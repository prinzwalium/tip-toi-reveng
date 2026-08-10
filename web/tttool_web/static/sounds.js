"use strict";

// The sound picker: the book's sound library, a microphone recorder and the
// speech synthesizer, in one dialog. book.js opens it for an area and gets the
// chosen sound back.

window.SoundPicker = (function () {
  var modal = document.getElementById("sound-modal");
  if (!modal) return { open: function () {} };

  var urls = document.getElementById("book-urls").dataset;
  var T = JSON.parse(document.getElementById("book-strings").textContent);
  function say(key) { return T[key] || key; }
  function url(template, value) { return template.replace(/AREA|SOUND|PATH/, encodeURIComponent(value)); }

  var list = document.getElementById("sound-list");
  var onPick = null;
  var sounds = [];
  var voices = [];
  var canSpeak = true;

  // ------------------------------------------------------------- helpers

  function post(target, data) {
    return fetch(target, { method: "POST", body: data, headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.json(); })
      .then(function (result) {
        if (result.error) throw new Error(result.error);
        if (result.sounds) remember(result);
        return result;
      });
  }

  function remember(result) {
    sounds = result.sounds || [];
    if (result.voices) voices = result.voices;
    if (typeof result.can_speak === "boolean") canSpeak = result.can_speak;
  }

  function load() {
    return fetch(urls.sounds, { headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.json(); })
      .then(function (result) { remember(result); renderList(); renderVoices(); });
  }

  function play(source) {
    var player = document.getElementById("sound-player");
    player.src = source;
    player.play();
  }

  // ------------------------------------------------------------ library

  function renderList() {
    list.textContent = "";
    if (!sounds.length) {
      var empty = document.createElement("p");
      empty.className = "muted empty";
      empty.textContent = say("No sounds yet — record one, let the computer speak, or upload a file.");
      list.appendChild(empty);
      return;
    }
    sounds.forEach(function (sound) {
      var row = document.createElement("div");
      row.className = "sound-row";

      var name = document.createElement("input");
      name.type = "text";
      name.value = sound.name;
      name.className = "sound-name-input";
      name.addEventListener("change", function () {
        var data = new FormData();
        data.append("name", name.value);
        post(url(urls.soundRename, sound.id), data).then(renderList);
      });
      row.appendChild(name);

      var used = document.createElement("span");
      used.className = "muted hint nowrap";
      used.textContent = sound.used
        ? say("used {count}×").replace("{count}", sound.used)
        : say("unused");
      row.appendChild(used);

      row.appendChild(button("▶", "ghost", function () { play(sound.url); }, say("Play")));
      row.appendChild(button(say("Use"), "", function () { choose(sound.id); }));
      row.appendChild(button("×", "ghost danger", function () {
        var question = sound.used
          ? say("This sound is used {count}× — delete it anyway?").replace("{count}", sound.used)
          : say("Delete this sound?");
        if (!window.confirm(question)) return;
        post(url(urls.soundDelete, sound.id)).then(function (result) {
          renderList();
          if (onPick) onPick(result, null);
        });
      }, say("Delete")));

      list.appendChild(row);
    });
  }

  function button(label, className, action, tip) {
    var element = document.createElement("button");
    element.type = "button";
    element.className = className;
    element.textContent = label;
    if (tip) element.setAttribute("data-tip", tip);
    element.addEventListener("click", action);
    return element;
  }

  function choose(soundId) {
    if (onPick) onPick(null, soundId);
    close();
  }

  // ------------------------------------------------------------ recording

  var recorder = null;
  var chunks = [];
  var recorded = null;
  var ticker = null;

  function recordError(message) {
    var box = document.getElementById("record-error");
    box.textContent = message;
    box.classList.toggle("hidden", !message);
  }

  document.getElementById("record-start").addEventListener("click", function () {
    recordError("");
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      recordError(say("This browser cannot record, or the page is not served over https."));
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      chunks = [];
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = function (event) { chunks.push(event.data); };
      recorder.onstop = function () {
        stream.getTracks().forEach(function (track) { track.stop(); });
        recorded = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        var preview = document.getElementById("record-preview");
        preview.src = URL.createObjectURL(recorded);
        preview.classList.remove("hidden");
        document.getElementById("record-actions").classList.remove("hidden");
      };
      recorder.start();
      var started = Date.now();
      ticker = window.setInterval(function () {
        document.getElementById("record-time").textContent =
          ((Date.now() - started) / 1000).toFixed(1) + " s";
      }, 100);
      document.getElementById("record-start").classList.add("hidden");
      document.getElementById("record-stop").classList.remove("hidden");
    }).catch(function () {
      recordError(say("No microphone available, or permission was refused."));
    });
  });

  document.getElementById("record-stop").addEventListener("click", function () {
    if (recorder && recorder.state !== "inactive") recorder.stop();
    window.clearInterval(ticker);
    document.getElementById("record-start").classList.remove("hidden");
    document.getElementById("record-stop").classList.add("hidden");
  });

  document.getElementById("record-discard").addEventListener("click", resetRecording);

  function resetRecording() {
    recorded = null;
    document.getElementById("record-preview").classList.add("hidden");
    document.getElementById("record-actions").classList.add("hidden");
    document.getElementById("record-time").textContent = "";
    document.getElementById("record-name").value = "";
  }

  document.getElementById("record-keep").addEventListener("click", function () {
    if (!recorded) return;
    var data = new FormData();
    data.append("sound", recorded, "aufnahme.webm");
    data.append("source", "record");
    data.append("name", document.getElementById("record-name").value);
    post(urls.soundAdd, data)
      .then(function (result) { resetRecording(); choose(result.sound); })
      .catch(function (error) { recordError(String(error.message || error)); });
  });

  // --------------------------------------------------------------- speech

  function renderVoices() {
    var select = document.getElementById("speak-language");
    if (select.options.length === voices.length && voices.length) return;
    select.textContent = "";
    voices.forEach(function (voice) {
      var option = document.createElement("option");
      option.value = voice.code;
      option.textContent = voice.label;
      select.appendChild(option);
    });
    document.getElementById("speak-go").disabled = !canSpeak;
    if (!canSpeak) speakError(say("This installation cannot speak text (no speech synthesizer installed)."));
  }

  function speakError(message) {
    var box = document.getElementById("speak-error");
    box.textContent = message;
    box.classList.toggle("hidden", !message);
  }

  document.getElementById("speak-go").addEventListener("click", function () {
    var text = document.getElementById("speak-text").value.trim();
    if (!text) return;
    speakError("");
    var data = new FormData();
    data.append("text", text);
    data.append("language", document.getElementById("speak-language").value);
    this.disabled = true;
    var self = this;
    post(urls.soundSpeak, data)
      .then(function (result) {
        document.getElementById("speak-text").value = "";
        choose(result.sound);
      })
      .catch(function (error) { speakError(String(error.message || error)); })
      .finally(function () { self.disabled = false; });
  });

  // -------------------------------------------------------------- upload

  document.getElementById("sound-upload").addEventListener("change", function () {
    if (!this.files.length) return;
    var data = new FormData();
    data.append("sound", this.files[0]);
    post(urls.soundAdd, data).then(function (result) { choose(result.sound); });
    this.value = "";
  });

  // --------------------------------------------------------------- shell

  var tabs = Array.prototype.slice.call(modal.querySelectorAll(".sound-tabs .tab"));

  function showTab(which) {
    tabs.forEach(function (tab) { tab.classList.toggle("active", tab.dataset.tab === which); });
    modal.querySelectorAll(".sound-panel").forEach(function (panel) {
      panel.classList.toggle("hidden", panel.dataset.panel !== which);
    });
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () { showTab(tab.dataset.tab); });
  });

  function close() {
    modal.classList.add("hidden");
    if (recorder && recorder.state === "recording") recorder.stop();
    window.clearInterval(ticker);
    onPick = null;
  }

  document.getElementById("sound-modal-close").addEventListener("click", close);
  modal.addEventListener("click", function (event) { if (event.target === modal) close(); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !modal.classList.contains("hidden")) close();
  });

  return {
    open: function (callback) {
      onPick = callback;
      modal.classList.remove("hidden");
      // Always start on the library: reusing a sound is the common case, and
      // an old tab left over from last time hides it.
      showTab("library");
      resetRecording();
      recordError("");
      speakError("");
      load();
    },
  };
})();
