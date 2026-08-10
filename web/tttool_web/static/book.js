"use strict";

// The book editor: a page picture with rectangles painted on it, in millimetres.
// The SVG viewBox is the page in mm, so screen ↔ page maths stays trivial.

(function () {
  var canvas = document.getElementById("canvas");
  if (!canvas) return;

  var urls = document.getElementById("book-urls").dataset;
  var T = JSON.parse(document.getElementById("book-strings").textContent);
  var book = JSON.parse(document.getElementById("book-data").textContent);
  var pageW = parseFloat(canvas.dataset.pageW);
  var pageH = parseFloat(canvas.dataset.pageH);

  var areasLayer = document.getElementById("areas");
  var picture = document.getElementById("page-picture");
  var saveState = document.getElementById("save-state");
  var currentPage = book.pages[0];
  var selectedId = null;
  var history = [];
  var saveTimer = null;

  function say(key) { return T[key] || key; }
  function url(template, value) { return template.replace(/PAGE|AREA|PATH/, encodeURIComponent(value)); }
  function area(id) { return currentPage.areas.filter(function (a) { return a.id === id; })[0]; }
  function selected() { return selectedId ? area(selectedId) : null; }

  // ------------------------------------------------------------- saving

  function snapshot() {
    history.push(JSON.stringify(book));
    if (history.length > 50) history.shift();
  }

  function saveNow() {
    window.clearTimeout(saveTimer);
    return fetch(urls.save, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
      body: JSON.stringify(book),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) throw new Error(data.error);
        saveState.textContent = say("Saved");
        saveState.className = "save-state";
      })
      .catch(function () {
        saveState.textContent = say("Could not save — is the server still running?");
        saveState.className = "save-state failed";
      });
  }

  function save() {
    window.clearTimeout(saveTimer);
    saveState.textContent = say("Saving …");
    saveState.className = "save-state saving";
    saveTimer = window.setTimeout(saveNow, 400);
  }

  // Uploads name an area or a page, so the server has to know about it first —
  // otherwise picking a sound right after drawing an area fails.
  function flush() {
    return saveNow();
  }

  function change() { render(); save(); }

  // ------------------------------------------------------------ drawing

  function render() {
    areasLayer.textContent = "";
    currentPage.areas.forEach(function (a) {
      var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "area" + (a.id === selectedId ? " selected" : "") +
        (a.sound ? "" : " silent"));
      g.dataset.id = a.id;

      var rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", a.x);
      rect.setAttribute("y", a.y);
      rect.setAttribute("width", a.w);
      rect.setAttribute("height", a.h);
      g.appendChild(rect);

      var label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", a.x + a.w / 2);
      label.setAttribute("y", a.y + a.h / 2);
      label.setAttribute("text-anchor", "middle");
      label.textContent = a.name || say("Area");
      g.appendChild(label);

      if (a.id === selectedId) {
        var handle = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        handle.setAttribute("class", "handle");
        handle.setAttribute("x", a.x + a.w - 3);
        handle.setAttribute("y", a.y + a.h - 3);
        handle.setAttribute("width", 6);
        handle.setAttribute("height", 6);
        handle.dataset.role = "resize";
        g.appendChild(handle);
      }
      areasLayer.appendChild(g);
    });
    renderSide();
  }

  function renderSide() {
    var a = selected();
    document.getElementById("area-empty").classList.toggle("hidden", !!a);
    document.getElementById("area-form").classList.toggle("hidden", !a);
    if (!a) return;
    document.getElementById("area-name").value = a.name || "";
    ["x", "y", "w", "h"].forEach(function (key) {
      document.getElementById("area-" + key).value = Math.round(a[key] * 10) / 10;
    });
    var hasSound = !!a.sound;
    document.getElementById("sound-play").classList.toggle("hidden", !hasSound);
    document.getElementById("sound-delete").classList.toggle("hidden", !hasSound);
    document.getElementById("sound-name").textContent = hasSound
      ? a.sound_name || a.sound
      : say("No sound yet — the area stays silent.");
  }

  function showPicture() {
    if (currentPage.image) {
      picture.setAttributeNS("http://www.w3.org/1999/xlink", "href", url(urls.raw, currentPage.image));
      picture.setAttribute("href", url(urls.raw, currentPage.image));
      picture.style.display = "";
    } else {
      picture.style.display = "none";
    }
  }

  // ---------------------------------------------------------- pointer

  function toPage(event) {
    var box = canvas.getBoundingClientRect();
    var scale = pageW / box.width;
    return {
      x: Math.max(0, Math.min(pageW, (event.clientX - box.left) * scale)),
      y: Math.max(0, Math.min(pageH, (event.clientY - box.top) * scale)),
    };
  }

  var drag = null;

  canvas.addEventListener("pointerdown", function (event) {
    var target = event.target.closest("g.area");
    var start = toPage(event);
    canvas.setPointerCapture(event.pointerId);

    if (target && event.target.dataset.role === "resize") {
      selectedId = target.dataset.id;
      drag = { mode: "resize", start: start, origin: Object.assign({}, area(selectedId)) };
    } else if (target) {
      selectedId = target.dataset.id;
      drag = { mode: "move", start: start, origin: Object.assign({}, area(selectedId)) };
    } else {
      // Dragging on empty space paints a new area.
      snapshot();
      var fresh = {
        id: nextId(), name: "", x: start.x, y: start.y, w: 1, h: 1, sound: "", sound_name: "",
      };
      currentPage.areas.push(fresh);
      selectedId = fresh.id;
      drag = { mode: "create", start: start, origin: fresh };
    }
    if (drag && drag.mode !== "create") snapshot();
    render();
  });

  canvas.addEventListener("pointermove", function (event) {
    if (!drag) return;
    var at = toPage(event);
    var a = selected();
    if (!a) return;
    if (drag.mode === "move") {
      a.x = clamp(drag.origin.x + (at.x - drag.start.x), 0, pageW - a.w);
      a.y = clamp(drag.origin.y + (at.y - drag.start.y), 0, pageH - a.h);
    } else if (drag.mode === "resize") {
      a.w = clamp(drag.origin.w + (at.x - drag.start.x), 3, pageW - a.x);
      a.h = clamp(drag.origin.h + (at.y - drag.start.y), 3, pageH - a.y);
    } else {
      a.x = Math.min(drag.start.x, at.x);
      a.y = Math.min(drag.start.y, at.y);
      a.w = Math.max(3, Math.abs(at.x - drag.start.x));
      a.h = Math.max(3, Math.abs(at.y - drag.start.y));
    }
    round(a);
    render();
  });

  canvas.addEventListener("pointerup", function () {
    if (!drag) return;
    drag = null;
    change();
  });

  function clamp(value, low, high) { return Math.max(low, Math.min(value, high)); }
  function round(a) {
    ["x", "y", "w", "h"].forEach(function (k) { a[k] = Math.round(a[k] * 10) / 10; });
  }

  function nextId() {
    var used = {};
    book.pages.forEach(function (p) { p.areas.forEach(function (a) { used[a.id] = 1; }); });
    var n = 1;
    while (used["a" + n]) n++;
    return "a" + n;
  }

  // ------------------------------------------------------------- form

  document.getElementById("area-name").addEventListener("input", function () {
    var a = selected();
    if (!a) return;
    a.name = this.value;
    render();
    save();
  });

  ["x", "y", "w", "h"].forEach(function (key) {
    document.getElementById("area-" + key).addEventListener("change", function () {
      var a = selected();
      if (!a) return;
      snapshot();
      a[key] = parseFloat(this.value) || 0;
      a.w = clamp(a.w, 3, pageW);
      a.h = clamp(a.h, 3, pageH);
      a.x = clamp(a.x, 0, pageW - a.w);
      a.y = clamp(a.y, 0, pageH - a.h);
      round(a);
      change();
    });
  });

  document.getElementById("area-delete").addEventListener("click", function () {
    var a = selected();
    if (!a || !window.confirm(say("Delete this area?"))) return;
    snapshot();
    currentPage.areas = currentPage.areas.filter(function (other) { return other !== a; });
    selectedId = null;
    change();
  });

  document.getElementById("add-area").addEventListener("click", function () {
    snapshot();
    var fresh = {
      id: nextId(), name: "", x: pageW / 2 - 15, y: pageH / 2 - 10, w: 30, h: 20,
      sound: "", sound_name: "",
    };
    currentPage.areas.push(fresh);
    selectedId = fresh.id;
    change();
  });

  document.getElementById("undo").addEventListener("click", undo);
  document.addEventListener("keydown", function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key === "z") { event.preventDefault(); undo(); }
    if (event.key === "Delete" && selected() && document.activeElement === document.body) {
      document.getElementById("area-delete").click();
    }
  });

  function undo() {
    var previous = history.pop();
    if (!previous) return;
    var restored = JSON.parse(previous);
    book.pages = restored.pages;
    currentPage = book.pages.filter(function (p) { return p.id === currentPage.id; })[0] || book.pages[0];
    selectedId = null;
    change();
  }

  // --------------------------------------------------------- uploads

  document.getElementById("page-image").addEventListener("change", function () {
    if (!this.files.length) return;
    var data = new FormData();
    data.append("image", this.files[0]);
    var pageId = currentPage.id;
    flush().then(function () {
      post(url(urls.image, pageId), data, function (result) {
        currentPage.image = result.image;
        showPicture();
      });
    });
    this.value = "";
  });

  document.getElementById("area-sound").addEventListener("change", function () {
    var a = selected();
    if (!a || !this.files.length) return;
    var data = new FormData();
    data.append("sound", this.files[0]);
    flush().then(function () {
      post(url(urls.sound, a.id), data, function (result) {
        a.sound = result.sound;
        a.sound_name = result.sound_name;
        render();
      });
    });
    this.value = "";
  });

  document.getElementById("sound-delete").addEventListener("click", function () {
    var a = selected();
    if (!a) return;
    post(url(urls.soundDelete, a.id), new FormData(), function () {
      a.sound = a.sound_name = "";
      render();
    });
  });

  document.getElementById("sound-play").addEventListener("click", function () {
    var a = selected();
    if (!a || !a.sound) return;
    var player = document.getElementById("sound-player");
    player.src = url(urls.raw, a.sound);
    player.play();
  });

  function post(target, data, done) {
    saveState.textContent = say("Saving …");
    fetch(target, { method: "POST", body: data, headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.json(); })
      .then(function (result) {
        if (result.error) throw new Error(result.error);
        saveState.textContent = say("Saved");
        saveState.className = "save-state";
        done(result);
      })
      .catch(function (error) {
        saveState.textContent = String(error.message || error);
        saveState.className = "save-state failed";
      });
  }

  // ----------------------------------------------------------- build

  document.getElementById("build").addEventListener("click", function () {
    var button = this;
    var box = document.getElementById("build-result");
    button.disabled = true;
    box.classList.remove("hidden");
    box.textContent = say("Building …");
    fetch(urls.build, { method: "POST", headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.json(); })
      .then(function (result) { showBuild(box, result); })
      .catch(function (error) { box.textContent = String(error); })
      .finally(function () { button.disabled = false; });
  });

  function showBuild(box, result) {
    box.textContent = "";
    if (result.error) { box.appendChild(note("problem", result.error)); return; }
    (result.problems || []).forEach(function (text) { box.appendChild(note("problem", text)); });
    (result.hints || []).forEach(function (text) { box.appendChild(note("hint", text)); });
    if (!result.ok) return;

    var done = document.createElement("div");
    done.className = "build-done";
    [[result.pdf_url, "1. " + (T["Print this"] || "Print this"), result.pdf],
     [result.gme_url, "2. " + (T["Copy this onto the pen"] || "Copy this onto the pen"), result.gme]]
      .forEach(function (entry) {
        if (!entry[0]) return;
        var link = document.createElement("a");
        link.className = "button";
        link.href = entry[0];
        link.textContent = entry[1];
        var line = document.createElement("div");
        line.className = "build-step";
        line.appendChild(link);
        var name = document.createElement("span");
        name.className = "muted";
        name.textContent = " " + entry[2];
        line.appendChild(name);
        done.appendChild(line);
      });
    box.appendChild(done);
  }

  function note(kind, text) {
    var element = document.createElement("p");
    element.className = kind === "problem" ? "note problem" : "note";
    element.textContent = text;
    return element;
  }

  // ------------------------------------------------------------ pages

  document.getElementById("page-picker").addEventListener("change", function () {
    currentPage = book.pages.filter(function (p) { return p.id === this.value; }, this)[0];
    selectedId = null;
    showPicture();
    render();
  });

  showPicture();
  render();
})();
