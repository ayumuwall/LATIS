"use strict";
(async () => {
  const info = document.getElementById("recording-info"), video = document.getElementById("recording");
  try {
    const response = await fetch("/api/recording", {cache:"no-store"});
    const result = await response.json();
    if (!response.ok || !result.ok || !result.data?.clips?.length) throw new Error("録画が未設定です。起動時に収録manifestを指定してください。");
    const data = result.data;
    function select(clip, index) {
      video.src = `/media/${index}.webm`;
      info.textContent = `${clip.title}\nDB: ${clip.database_id}\n収録: ${clip.recorded_at}\n対象: rev ${clip.from_revision} → ${clip.to_revision}\nモデル: ${clip.model} / effort ${clip.effort}\n${clip.note}`;
      document.querySelectorAll("#clips button").forEach((button,i) => button.setAttribute("aria-pressed",String(i === index)));
    }
    data.clips.forEach((clip,index) => {
      const button = document.createElement("button"); button.textContent = clip.title;
      button.addEventListener("click", () => select(clip,index)); document.getElementById("clips").append(button);
    });
    select(data.clips[0],0);
  } catch (error) {info.textContent = error.message; video.hidden = true;}
})();
