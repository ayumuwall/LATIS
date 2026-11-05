#!/usr/bin/env python3
"""M5の架空100ノードを、隔離下の変更・JSON復元・独立セッションで検証する。"""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from latis import Engine
from scripts import llm_acceptance as acceptance


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def reviewed(directory):
    review = acceptance.load_json(directory / 'semantic-review.json')
    require(review.get('passed') is True and review.get('notes'), '実記録の意味レビューが未完了です。')
    return review


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    directory = acceptance.prepare_case(output / 'explicit', 'explicit')
    facts = acceptance.load_json(directory / 'fixture.json')
    fixture = acceptance.Fixture(directory / 'workspace')
    fixture.ids = facts['ids']
    original_ids = set(fixture.ids.values())
    fixture.apply(acceptance.make_node('operations', '運用全体の分類', '架空の運用分類。効力や権限の階層ではない。', 'scope'),
                  acceptance.make_node('reports', '帳票出力の分類', 'ログ保持とは別の架空の帳票規則。', 'scope'))
    for start in (0, 43):
        operations = []
        for number in range(start, start + 43):
            ref = f'report_{number:02d}'
            operations.extend((acceptance.make_node(ref, f'帳票{number:02d}の配送', f'帳票{number:02d}は標準経路で配送する。'),
                               acceptance.make_relation(ref + '_scope', '$' + ref, fixture.ids['reports'], 'scoped_to')))
        fixture.apply(*operations)
    fixture.save(acceptance.make_node('memo', '未分類の運用メモ', '通常ログと監査ログは別々の合意。分類が未整理でも原文から調べる。', 'artifact', 'draft'),
                 acceptance.make_node('proposal', '未採択の保持期間案', '通常ログを30日に延ばす案は未決定であり、採択済みの期間ではない。', 'proposal', 'proposed'),
                 acceptance.make_node('question', '将来の索引の未解決事項', '帳票の検索索引を増やすかは未決定。今回のログ期間の改訂には関係しない。', 'question', 'draft'))
    fixture.save(acceptance.make_relation('candidate', fixture.ids['proposal'], fixture.ids['normal_retention'], 'supports', 'candidate'))
    fixture.apply(acceptance.make_node('exception', '帳票00の緊急再送', '帳票00の緊急再送時だけ専用経路で配送する。'),
                  acceptance.make_relation('exception_link', '$exception', fixture.ids['report_00'], 'exception_to', qualifier='帳票00の緊急再送時に限る。'),
                  acceptance.make_relation('exception_scope', '$exception', fixture.ids['reports'], 'scoped_to'),
                  acceptance.make_relation('normal_second_scope', fixture.ids['normal_retention'], fixture.ids['operations'], 'scoped_to'),
                  acceptance.make_relation('report_hierarchy', fixture.ids['operations'], fixture.ids['reports'], 'contains'))
    facts.update(ids=fixture.ids, before=fixture.snapshot())
    require(len(facts['before']['nodes']) == 100, '代表データが100ノードではありません。')
    acceptance.write_json(directory / 'fixture.json', facts)
    side_nodes = [node['id'] for node in facts['before']['nodes'] if node['id'] not in original_ids]
    side_relations = [rel['id'] for rel in facts['before']['relations'] if rel['id'] in set(fixture.ids.values()) - original_ids]
    acceptance.write_json(output / 'dataset.json', dict(initial_nodes=100, side_node_ids=side_nodes, side_relation_ids=side_relations,
        features=['unscoped', 'multiple_scopes', 'candidate', 'exception', 'question', 'implemented_by', 'verified_by'],
        sources={str(path.relative_to(ROOT)): acceptance.sha(path) for path in sorted([*ROOT.glob('latis/*.py'), Path(__file__).resolve(), ROOT / 'scripts/llm_acceptance.py', ROOT / 'scripts/claude_sandbox.py', ROOT / 'scripts/test_support.py', ROOT / 'docs/v0.3.0/LATIS_LLM_Guide.md', ROOT / 'docs/v0.3.0/LATIS_API.md'])}))
    # CLIの起動時間も含む経過時間を、LLM通信・推論を含むセッション時間と別に測る。
    tool = directory / 'tool/latis'
    original = tool.with_name('latis-original')
    tool.rename(original)
    tool.write_text(f'''#!{Path(sys.executable).resolve()}
import fcntl, json, subprocess, sys, time
started = time.monotonic()
result = subprocess.run([{str(original)!r}, *sys.argv[1:]])
record = dict(operation='cli_timing', seconds=time.monotonic()-started, exit_code=result.returncode)
with open({str(directory / 'helpers.jsonl')!r}, 'a') as stream:
    fcntl.flock(stream, fcntl.LOCK_EX)
    stream.write(json.dumps(record)+'\\n')
raise SystemExit(result.returncode)
''')
    tool.chmod(0o755)
    print('代表データの準備完了: 100ノード。全登録は通常のconsult/apply/save-draftを使用。', flush=True)


def unchanged(output):
    for relative, digest in acceptance.load_json(output / 'dataset.json')['sources'].items():
        require(acceptance.sha(ROOT / relative) == digest, '対象ソースが変わりました: ' + relative)


def launch(output, name):
    unchanged(output)
    directory = output / name
    require(not (directory / 'initial-result.json').exists(), '同じ実行記録を上書きしません。')
    started = time.monotonic()
    result = acceptance.run_claude(directory)
    acceptance.write_json(directory / 'timing.json', dict(wall_seconds=time.monotonic()-started,
        claude_duration_ms=result['result']['duration_ms'], claude_api_duration_ms=result['result'].get('duration_api_ms')))
    report = acceptance.evaluate(directory)
    require(report['mechanical_pass'], '機械検査が不合格です。後続の検証を停止します。')
    unchanged(output)
    print('実応答・操作・DB差分をレビューし、semantic-review.jsonへ判定を保存してください。', flush=True)


def handover(output):
    reviewed(output / 'explicit')
    fixture = acceptance.Fixture(output / 'explicit/workspace')
    transfer = output / 'json-restored'
    workspace = transfer / 'workspace'
    workspace.mkdir(parents=True, exist_ok=False)
    snapshot = output / 'final.json'
    fixture.call('export', dict(format='json', destination=str(snapshot)))
    restored = Engine(workspace / 'demo.sqlite').execute('restore', dict(format='json', source=str(snapshot)))
    require(restored['ok'], '完全JSONの復元に失敗しました。')
    require(acceptance.Fixture(workspace).snapshot() == fixture.snapshot(), 'JSON復元で全記録が一致しません。')
    for path in fixture.workspace.iterdir():
        if path.is_file() and (path.name in {'retention.py', 'test_retention.py', 'baseline-test.log'} or path.match('test-result-*.log')):
            shutil.copyfile(path, workspace / path.name)
    facts = acceptance.load_json(output / 'explicit/fixture.json')
    acceptance.write_json(transfer / 'fixture.json', dict(ids=facts['ids']))
    acceptance.prepare_case(output / 'handover', 'handover', handover_source=transfer)
    launch(output, 'handover')


def report(output):
    unchanged(output)
    dataset = acceptance.load_json(output / 'dataset.json')
    facts = acceptance.load_json(output / 'explicit/fixture.json')
    before = facts['before']
    after = acceptance.load_json(output / 'explicit/after.json')
    for collection, field in (('nodes', 'side_node_ids'), ('relations', 'side_relation_ids')):
        old = {item['id']: item for item in before[collection]}
        new = {item['id']: item for item in after[collection]}
        require(all(old[id_] == new[id_] for id_ in dataset[field]), '無関係の代表データが変更されました。')
    cases = {}
    for name in ('explicit', 'handover'):
        directory = output / name
        check = acceptance.load_json(directory / 'check.json')
        require(check['mechanical_pass'], '機械検査が未完了です。')
        cases[name] = dict(check=check, semantic_review=reviewed(directory), timing=acceptance.load_json(directory / 'timing.json'))
    helpers = [json.loads(line) for line in (output / 'explicit/helpers.jsonl').read_text().splitlines()]
    timings = [item['seconds'] for item in helpers if item['operation'] == 'cli_timing']
    require(len(timings) == cases['explicit']['check']['calls'], 'CLIの時間記録が不足しています。')
    result = dict(passed=True, initial_nodes=len(before['nodes']), final_nodes=len(after['nodes']),
        kinds=dict(Counter(node['kind'] for node in before['nodes'])), features=dataset['features'],
        unrelated_records_preserved=True, full_json_restore_identical=True, cases=cases,
        cli_wall_seconds=sum(timings), timing_note='CLI時間はPython起動・IPCを含む。セッション時間とAPI時間はClaude CLIの実測。20万合意の性能評価ではない。')
    acceptance.write_json(output / 'report.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='専用の出力先。prepare時は未存在であること')
    parser.add_argument('--stage', required=True, choices=('prepare', 'change', 'handover', 'report'))
    args = parser.parse_args()
    destination = Path(args.output).resolve()
    if args.stage == 'prepare':
        prepare(destination)
    elif args.stage == 'change':
        launch(destination, 'explicit')
    elif args.stage == 'handover':
        handover(destination)
    else:
        report(destination)
