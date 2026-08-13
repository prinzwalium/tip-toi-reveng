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
  var future = [];
  var saveTimer = null;

  function say(key) { return T[key] || key; }
  function url(template, value) { return template.replace(/PAGE|AREA|PATH|GROUP/, encodeURIComponent(value)); }
  function area(id) { return currentPage.areas.filter(function (a) { return a.id === id; })[0]; }
  function soundOf(a) {
    if (!a || !a.sound_id) return null;
    return (book.sounds || []).filter(function (s) { return s.id === a.sound_id; })[0] || null;
  }
  function selected() { return selectedId ? area(selectedId) : null; }

  // ------------------------------------------------------------- saving

  function snapshot() {
    history.push(JSON.stringify(book));
    if (history.length > 50) history.shift();
    future.length = 0;   // a new change ends the redo chain
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

  function change() { render(); save(); updateGuide(); }

  // ------------------------------------------------------------ drawing

  function svg(tag, attributes) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attributes || {}).forEach(function (key) {
      node.setAttribute(key, attributes[key]);
    });
    return node;
  }

  function isPolygon(a) { return a.kind === "poly" && a.points && a.points.length >= 3; }

  function describe(a) {
    var sound = soundOf(a);
    return say("Area {name}, {x} by {y} millimetres, {sound}")
      .replace("{name}", a.name || say("Area"))
      .replace("{x}", Math.round(a.x))
      .replace("{y}", Math.round(a.y))
      .replace("{sound}", sound
        ? say("plays {sound}").replace("{sound}", sound.name || sound.id)
        : say("no sound yet"));
  }

  function render() {
    areasLayer.textContent = "";
    currentPage.areas.forEach(function (a) {
      var g = svg("g", {
        class: "area" + (a.id === selectedId ? " selected" : "") + (a.sound_id ? "" : " silent"),
        // Reachable and describable without a mouse: Tab walks the areas of
        // the page, and the label says which one and what it does.
        tabindex: "0",
        role: "button",
        "aria-label": describe(a),
      });
      g.dataset.id = a.id;

      if (isPolygon(a)) {
        g.appendChild(svg("polygon", {
          points: a.points.map(function (p) { return p[0] + "," + p[1]; }).join(" "),
        }));
      } else {
        g.appendChild(svg("rect", { x: a.x, y: a.y, width: a.w, height: a.h }));
      }

      // Top left corner rather than the middle: the label names the area
      // without covering the part of the picture the area is drawn around.
      var label = svg("text", { x: a.x + 1.2, y: a.y + 3 });
      label.textContent = a.name || say("Area");
      g.appendChild(label);

      if (a.id === selectedId) {
        if (isPolygon(a)) {
          a.points.forEach(function (point, index) {
            var handle = svg("circle", { class: "handle", cx: point[0], cy: point[1], r: 2 });
            handle.dataset.role = "point";
            handle.dataset.index = index;
            g.appendChild(handle);
          });
        } else {
          var handle = svg("rect", {
            class: "handle", x: a.x + a.w - 3, y: a.y + a.h - 3, width: 6, height: 6,
          });
          handle.dataset.role = "resize";
          g.appendChild(handle);
        }
      }
      areasLayer.appendChild(g);
    });

    // The polygon being drawn right now.
    if (drawing) {
      var preview = svg("polyline", {
        class: "drawing",
        points: drawing.points.map(function (p) { return p[0] + "," + p[1]; }).join(" "),
      });
      areasLayer.appendChild(preview);
      drawing.points.forEach(function (point) {
        areasLayer.appendChild(svg("circle", { class: "drawing-point", cx: point[0], cy: point[1], r: 1.6 }));
      });
    }
    renderSide();
    renderAreaList();
  }

  //: Below this an area is hard for the pen to hit; the server checks the same.
  var MIN_AREA_MM = 10;

  // Every area of the page as a row, because an area three millimetres wide,
  // or one hidden under another, cannot realistically be clicked on the page.
  function renderAreaList() {
    var list = document.getElementById("area-list");
    var count = document.getElementById("area-count");
    list.textContent = "";
    count.textContent = "(" + currentPage.areas.length + ")";

    if (!currentPage.areas.length) {
      var empty = document.createElement("li");
      empty.className = "muted empty";
      empty.textContent = say("No areas yet — drag one onto the picture.");
      list.appendChild(empty);
      return;
    }

    currentPage.areas.forEach(function (a) {
      var sound = soundOf(a);
      var row = document.createElement("li");
      row.className = "area-row" + (a.id === selectedId ? " selected" : "");
      row.dataset.id = a.id;

      var pick = document.createElement("button");
      pick.type = "button";
      pick.className = "area-pick";
      pick.textContent = a.name || say("Area");
      pick.addEventListener("click", function () { selectArea(a.id); });
      row.appendChild(pick);

      if (!isPolygon(a) && (a.w < MIN_AREA_MM || a.h < MIN_AREA_MM)) {
        var small = document.createElement("span");
        small.className = "badge warn";
        small.textContent = say("too small");
        row.appendChild(small);
      }

      var what = document.createElement("span");
      what.className = "area-sound muted grow";
      what.textContent = sound ? (sound.name || sound.id) : say("no sound yet");
      if (!sound) what.classList.add("silent");
      row.appendChild(what);

      if (sound) {
        row.appendChild(smallButton("▶", "ghost", function () { playFile(sound.file); }));
      }
      row.appendChild(
        smallButton(say("Sound …"), "ghost", function () { chooseSoundFor(a); })
      );
      var remove = smallButton("×", "ghost danger", function () { removeArea(a); });
      remove.setAttribute("aria-label", say("Delete area"));
      row.appendChild(remove);

      // Pointing at a row lights the area up on the page, which is how you
      // find the one you are looking at.
      row.addEventListener("mouseenter", function () { highlight(a.id, true); });
      row.addEventListener("mouseleave", function () { highlight(a.id, false); });
      list.appendChild(row);
    });
  }

  function highlight(id, on) {
    var node = areasLayer.querySelector('[data-id="' + id + '"]');
    if (node) node.classList.toggle("highlight", on);
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
    var sound = soundOf(a);
    document.getElementById("sound-play").classList.toggle("hidden", !sound);
    document.getElementById("sound-clear").classList.toggle("hidden", !sound);
    document.getElementById("sound-name").textContent = sound
      ? sound.name || sound.id
      : say("No sound yet — the area stays silent.");

    document.getElementById("area-behaviour").value = a.behaviour || "play";
    document.getElementById("area-script").value = a.script || "";
    document.getElementById("area-correct").checked = !!a.correct;
    showBehaviour(a.behaviour || "play");
    renderManySounds(a);
    renderGroups(a);
  }

  // Only the panels that belong to the chosen behaviour are shown.
  function showBehaviour(behaviour) {
    $$("#area-form [data-for]").forEach(function (panel) {
      panel.classList.toggle("hidden", panel.dataset.for.split(" ").indexOf(behaviour) < 0);
    });
    var hint = document.getElementById("many-hint");
    hint.textContent = behaviour === "sequence"
      ? say("One sound per tap, in this order; then it starts again.")
      : say("The pen picks one of these each time.");
  }

  function $$(selector) {
    return Array.prototype.slice.call(document.querySelectorAll(selector));
  }

  function renderManySounds(a) {
    var box = document.getElementById("sound-many");
    box.textContent = "";
    (a.sound_ids || []).forEach(function (soundId, index) {
      var entry = (book.sounds || []).filter(function (s) { return s.id === soundId; })[0];
      var row = document.createElement("div");
      row.className = "sound-row";
      var label = document.createElement("span");
      label.className = "grow";
      label.textContent = (index + 1) + ". " + (entry ? entry.name || entry.id : soundId);
      row.appendChild(label);
      row.appendChild(smallButton("▶", "ghost", function () {
        if (entry) playFile(entry.file);
      }));
      row.appendChild(smallButton("↑", "ghost", function () {
        if (index === 0) return;
        snapshot();
        a.sound_ids.splice(index - 1, 0, a.sound_ids.splice(index, 1)[0]);
        change();
      }));
      row.appendChild(smallButton("×", "ghost danger", function () {
        snapshot();
        a.sound_ids.splice(index, 1);
        change();
      }));
      box.appendChild(row);
    });
  }

  function smallButton(label, className, action) {
    var element = document.createElement("button");
    element.type = "button";
    element.className = className;
    element.textContent = label;
    element.addEventListener("click", action);
    return element;
  }

  function playFile(file) {
    var player = document.getElementById("sound-player");
    player.src = url(urls.raw, file);
    player.play();
  }

  function renderGroups(a) {
    var select = document.getElementById("area-group");
    select.textContent = "";
    var kind = a.behaviour === "collect" ? "collect" : "quiz";
    (book.groups || []).filter(function (g) { return g.kind === kind; }).forEach(function (group) {
      var option = document.createElement("option");
      option.value = group.id;
      option.textContent = group.name || group.id;
      if (group.id === a.group) option.selected = true;
      select.appendChild(option);
    });
    var fresh = document.createElement("option");
    fresh.value = "+";
    fresh.textContent = say("+ New game");
    select.appendChild(fresh);

    var settings = document.getElementById("group-settings");
    settings.textContent = "";
    var group = (book.groups || []).filter(function (g) { return g.id === a.group; })[0];
    if (!group) return;

    var fields = group.kind === "quiz"
      ? [["right_sound_id", say("Sound for a right answer")],
         ["wrong_sound_id", say("Sound for a wrong answer")]]
      : [["reward_sound_id", say("Reward when everything is found")]];
    fields.forEach(function (entry) {
      var row = document.createElement("div");
      row.className = "sound-row";
      var label = document.createElement("span");
      label.className = "grow hint";
      var chosen = (book.sounds || []).filter(function (s) { return s.id === group[entry[0]]; })[0];
      label.textContent = entry[1] + ": " + (chosen ? chosen.name || chosen.id : say("none"));
      row.appendChild(label);
      row.appendChild(smallButton(say("Choose"), "ghost", function () {
        flush().then(function () {
          window.SoundPicker.open(function (library, soundId) {
            if (!soundId) return;
            var data = new FormData();
            data.append(entry[0], soundId);
            post(url(urls.groupUpdate, group.id), data, function (result) {
              book.groups = result.book.groups;
              book.sounds = (library && library.sounds) || book.sounds;
              render();
            });
          });
        });
      }));
      settings.appendChild(row);
    });
  }

  function showPicture() {
    if (currentPage.image) {
      // The preview is a smaller copy of the same picture; the original stays
      // on the server for printing. A book made before previews existed, or a
      // picture too small to be worth shrinking, has none.
      var shown = url(urls.raw, currentPage.preview || currentPage.image);
      picture.setAttributeNS("http://www.w3.org/1999/xlink", "href", shown);
      picture.setAttribute("href", shown);
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

    // Drawing a free shape: every click drops a corner, and clicking the first
    // corner again closes it. (A double click would be nicer, but re-drawing
    // the preview swaps the element under the cursor, so the browser never
    // reports one.)
    if (drawing) {
      var first = drawing.points[0];
      if (first && drawing.points.length >= 3 &&
          Math.abs(first[0] - start.x) < CLOSE_DISTANCE &&
          Math.abs(first[1] - start.y) < CLOSE_DISTANCE) {
        finishDrawing();
        return;
      }
      drawing.points.push([round1(start.x), round1(start.y)]);
      render();
      return;
    }

    canvas.setPointerCapture(event.pointerId);

    if (target && event.target.dataset.role === "point") {
      selectedId = target.dataset.id;
      snapshot();
      drag = { mode: "point", index: parseInt(event.target.dataset.index, 10) };
      return;
    }
    if (target && event.target.dataset.role === "resize") {
      selectedId = target.dataset.id;
      drag = { mode: "resize", start: start, origin: Object.assign({}, area(selectedId)) };
    } else if (target) {
      selectedId = target.dataset.id;
      var picked = area(selectedId);
      drag = {
        mode: "move", start: start,
        origin: Object.assign({}, picked, { points: (picked.points || []).map(function (p) { return p.slice(); }) }),
      };
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
    if (drag.mode === "point") {
      a.points[drag.index] = [round1(at.x), round1(at.y)];
      boundingBox(a);
      render();
      return;
    }
    if (drag.mode === "move") {
      var nx = clamp(drag.origin.x + (at.x - drag.start.x), 0, pageW - a.w);
      var ny = clamp(drag.origin.y + (at.y - drag.start.y), 0, pageH - a.h);
      if (isPolygon(a)) {
        var dx = nx - drag.origin.x, dy = ny - drag.origin.y;
        a.points = drag.origin.points.map(function (p) {
          return [round1(p[0] + dx), round1(p[1] + dy)];
        });
      }
      a.x = nx;
      a.y = ny;
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

  function moveArea(a, x, y) {
    var nx = clamp(x, 0, pageW - a.w);
    var ny = clamp(y, 0, pageH - a.h);
    if (isPolygon(a)) {
      var dx = nx - a.x, dy = ny - a.y;
      a.points = a.points.map(function (p) { return [round1(p[0] + dx), round1(p[1] + dy)]; });
    }
    a.x = nx;
    a.y = ny;
    round(a);
  }

  function resizeArea(a, w, h) {
    // A free shape has no width and height of its own — its corners are its
    // shape, and those are moved one by one.
    if (isPolygon(a)) return;
    a.w = clamp(w, 3, pageW - a.x);
    a.h = clamp(h, 3, pageH - a.y);
    round(a);
  }
  function round1(value) { return Math.round(value * 10) / 10; }
  function round(a) {
    ["x", "y", "w", "h"].forEach(function (k) { a[k] = round1(a[k]); });
  }

  function boundingBox(a) {
    if (!isPolygon(a)) return;
    var xs = a.points.map(function (p) { return p[0]; });
    var ys = a.points.map(function (p) { return p[1]; });
    a.x = Math.min.apply(null, xs);
    a.y = Math.min.apply(null, ys);
    a.w = Math.max(Math.max.apply(null, xs) - a.x, 1);
    a.h = Math.max(Math.max.apply(null, ys) - a.y, 1);
    round(a);
  }

  // ------------------------------------------------------ free shapes

  var drawing = null;
  var polygonButton = document.getElementById("add-polygon");
  var polygonLabel = polygonButton.textContent;
  //: How close to the first corner a click has to be to close the shape, in mm.
  var CLOSE_DISTANCE = 5;

  function startDrawing() {
    drawing = { points: [] };
    document.getElementById("canvas-hint").textContent =
      say("Click the corners; click the first one again to close the shape.");
    polygonButton.classList.add("active");
    polygonButton.textContent = say("Done");
  }

  function finishDrawing() {
    var points = drawing ? drawing.points : [];
    drawing = null;
    polygonButton.classList.remove("active");
    polygonButton.textContent = polygonLabel;
    document.getElementById("canvas-hint").textContent = say("Drag on the picture to create an area.");
    if (points.length < 3) { render(); return; }
    snapshot();
    var fresh = {
      id: nextId(), name: "", kind: "poly", points: points,
      x: 0, y: 0, w: 1, h: 1, sound: "", sound_name: "",
    };
    boundingBox(fresh);
    currentPage.areas.push(fresh);
    selectedId = fresh.id;
    change();
  }

  document.getElementById("add-polygon").addEventListener("click", function () {
    if (drawing) finishDrawing(); else startDrawing();
  });

  canvas.addEventListener("dblclick", function (event) {
    if (drawing) { event.preventDefault(); finishDrawing(); }
  });

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

  // -------------------------------------------------- behaviours

  document.getElementById("area-behaviour").addEventListener("change", function () {
    var a = selected();
    if (!a) return;
    snapshot();
    a.behaviour = this.value;
    // Moving to "one of several" starts from the sound already chosen.
    if ((a.behaviour === "random" || a.behaviour === "sequence") &&
        !(a.sound_ids || []).length && a.sound_id) {
      a.sound_ids = [a.sound_id];
    }
    if ((a.behaviour === "answer" || a.behaviour === "collect") && !a.group) {
      var kind = a.behaviour === "collect" ? "collect" : "quiz";
      var existing = (book.groups || []).filter(function (g) { return g.kind === kind; })[0];
      if (existing) {
        a.group = existing.id;
      } else {
        newGroup(kind);
        return;
      }
    }
    change();
  });

  document.getElementById("area-correct").addEventListener("change", function () {
    var a = selected();
    if (!a) return;
    a.correct = this.checked;
    change();
  });

  document.getElementById("area-script").addEventListener("change", function () {
    var a = selected();
    if (!a) return;
    snapshot();
    a.script = this.value;
    change();
  });

  document.getElementById("sound-add").addEventListener("click", function () {
    var a = selected();
    if (!a) return;
    flush().then(function () {
      window.SoundPicker.open(function (library, soundId) {
        if (library && library.sounds) book.sounds = library.sounds;
        if (!soundId) { render(); return; }
        snapshot();
        a.sound_ids = (a.sound_ids || []).concat([soundId]);
        change();
      });
    });
  });

  document.getElementById("area-group").addEventListener("change", function () {
    var a = selected();
    if (!a) return;
    if (this.value === "+") {
      newGroup(a.behaviour === "collect" ? "collect" : "quiz");
      return;
    }
    a.group = this.value;
    change();
  });

  function newGroup(kind) {
    var a = selected();
    var data = new FormData();
    data.append("kind", kind);
    flush().then(function () {
      post(urls.groupAdd, data, function (result) {
        book.groups = result.book.groups;
        a.group = result.group;
        change();
      });
    });
  }

  document.getElementById("area-delete").addEventListener("click", function () {
    removeArea(selected());
  });

  // Deleting an area can be undone, so it does not ask first — it says what
  // happened and offers to put it back, which is quicker than a dialog for
  // the usual case: clearing away several areas drawn by accident.
  function removeArea(a) {
    if (!a) return;
    var name = a.name || say("Area");
    snapshot();
    currentPage.areas = currentPage.areas.filter(function (other) { return other !== a; });
    if (selectedId === a.id) selectedId = null;
    change();
    toast(say("“{name}” deleted.").replace("{name}", name), say("Undo"), undo);
  }

  var toastTimer = null;
  function toast(message, actionLabel, action) {
    var box = document.getElementById("toast");
    box.textContent = message + " ";
    if (action) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "ghost";
      button.textContent = actionLabel;
      button.addEventListener("click", function () {
        action();
        hideToast();
      });
      box.appendChild(button);
    }
    box.classList.remove("hidden");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(hideToast, 8000);
  }

  function hideToast() {
    window.clearTimeout(toastTimer);
    document.getElementById("toast").classList.add("hidden");
  }

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

  // -- the editor without a mouse ---------------------------------------
  //
  // Tab reaches every area, Enter/Space selects it, the arrow keys move it
  // and + / − change its size. Everything else on the page is ordinary form
  // controls, which the browser already handles.

  var ARROWS = {
    ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
  };

  function focusedArea() {
    var node = document.activeElement;
    while (node && node !== areasLayer) {
      if (node.dataset && node.dataset.id) return area(node.dataset.id);
      node = node.parentNode;
    }
    return null;
  }

  function keepFocus(id) {
    var node = areasLayer.querySelector('[data-id="' + id + '"]');
    if (node && node.focus) node.focus();
  }

  //: Nudging with the keyboard should end up as one undo step, not thirty.
  var nudging = null;
  function nudge(a, move) {
    if (nudging !== a.id) {
      snapshot();
      nudging = a.id;
      window.setTimeout(function () { nudging = null; }, 1500);
    }
    move();
    change();
    keepFocus(a.id);
  }

  function selectArea(id) {
    selectedId = id;
    render();  // renders the side panel too
    keepFocus(id);
  }

  areasLayer.addEventListener("focusin", function (event) {
    var node = event.target;
    if (node.dataset && node.dataset.id && node.dataset.id !== selectedId) {
      selectArea(node.dataset.id);
    }
  });

  areasLayer.addEventListener("keydown", function (event) {
    var a = focusedArea();
    if (!a) return;

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectArea(a.id);
      return;
    }

    var step = ARROWS[event.key];
    if (step) {
      event.preventDefault();
      var distance = event.shiftKey ? 5 : 1;
      nudge(a, function () { moveArea(a, a.x + step[0] * distance, a.y + step[1] * distance); });
      return;
    }

    if (event.key === "+" || event.key === "-") {
      event.preventDefault();
      var by = (event.key === "+" ? 1 : -1) * (event.shiftKey ? 5 : 1);
      nudge(a, function () { resizeArea(a, a.w + by, a.h + by); });
    }
  });

  document.addEventListener("keydown", function (event) {
    if (drawing && event.key === "Enter") { event.preventDefault(); finishDrawing(); return; }
    if (drawing && event.key === "Escape") {
      event.preventDefault();
      drawing.points = [];
      finishDrawing();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      if (event.shiftKey) redo(); else undo();
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
      event.preventDefault();
      redo();
    }
    if (event.key === "Delete" && selected() && document.activeElement === document.body) {
      document.getElementById("area-delete").click();
    }
  });

  function undo() {
    var previous = history.pop();
    if (!previous) return;
    future.push(JSON.stringify(book));
    apply(JSON.parse(previous));
  }

  function redo() {
    var next = future.pop();
    if (!next) return;
    history.push(JSON.stringify(book));
    apply(JSON.parse(next));
  }

  function apply(restored) {
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
        currentPage.preview = result.preview || "";
        showPicture();
      });
    });
    this.value = "";
  });

  document.getElementById("sound-choose").addEventListener("click", function () {
    chooseSoundFor(selected());
  });

  function chooseSoundFor(a) {
    if (!a) return;
    // Whichever way the picker was opened, the panel and the page now show
    // the area the chosen sound is about to land on.
    if (selectedId !== a.id) selectArea(a.id);
    flush().then(function () {
      window.SoundPicker.open(function (library, soundId) {
        if (library && library.sounds) book.sounds = library.sounds;
        if (library && library.book) {   // a sound was deleted while picking
          book.pages = library.book.pages;
          currentPage = book.pages.filter(function (p) { return p.id === currentPage.id; })[0];
          render();
          return;
        }
        if (!soundId) { render(); return; }
        var data = new FormData();
        data.append("sound_id", soundId);
        post(url(urls.soundAssign, a.id), data, function (result) {
          book.pages = result.book.pages;
          book.sounds = result.sounds;
          currentPage = book.pages.filter(function (p) { return p.id === currentPage.id; })[0];
          render();
        });
      });
    });
  }

  document.getElementById("sound-clear").addEventListener("click", function () {
    var a = selected();
    if (!a) return;
    var data = new FormData();
    data.append("sound_id", "");
    post(url(urls.soundAssign, a.id), data, function (result) {
      book.pages = result.book.pages;
      currentPage = book.pages.filter(function (p) { return p.id === currentPage.id; })[0];
      render();
    });
  });

  document.getElementById("sound-play").addEventListener("click", function () {
    var sound = soundOf(selected());
    if (!sound) return;
    var player = document.getElementById("sound-player");
    player.src = url(urls.raw, sound.file);
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
    [[result.test_pdf_url, say("Print test page first"), result.test_pdf],
     [result.pdf_url, "1. " + say("Print this"), result.pdf],
     [result.gme_url, "2. " + say("Copy this onto the pen"), result.gme],
     [result.control_pdf_url, say("Comparison sheet from tttool"), result.control_pdf]]
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

  var picker = document.getElementById("page-picker");
  var pageName = document.getElementById("page-name");

  function renderPages() {
    picker.textContent = "";
    book.pages.forEach(function (page, index) {
      var option = document.createElement("option");
      option.value = page.id;
      option.textContent = page.name || say("Page {number}").replace("{number}", index + 1);
      if (page.id === currentPage.id) option.selected = true;
      picker.appendChild(option);
    });
    pageName.value = currentPage.name || "";
    document.getElementById("page-delete").disabled = book.pages.length < 2;
  }

  function showPage(pageId) {
    currentPage = book.pages.filter(function (p) { return p.id === pageId; })[0] || book.pages[0];
    selectedId = null;
    drawing = null;
    renderPages();
    showPicture();
    render();
  }

  picker.addEventListener("change", function () { showPage(this.value); });

  pageName.addEventListener("input", function () {
    currentPage.name = this.value;
    renderPages();
    save();
  });

  function pageAction(target, confirmText) {
    if (confirmText && !window.confirm(confirmText)) return;
    flush().then(function () {
      post(target, new FormData(), function (result) {
        book.pages = result.book.pages;
        showPage(result.page);
      });
    });
  }

  document.getElementById("page-add").addEventListener("click", function () {
    pageAction(urls.pageAdd);
  });
  document.getElementById("page-duplicate").addEventListener("click", function () {
    pageAction(url(urls.pageDuplicate, currentPage.id));
  });
  document.getElementById("page-delete").addEventListener("click", function () {
    pageAction(url(urls.pageDelete, currentPage.id), say("Delete this page with everything on it?"));
  });
  document.getElementById("page-up").addEventListener("click", function () {
    pageAction(url(urls.pageMove, currentPage.id) + "?direction=up");
  });
  document.getElementById("page-down").addEventListener("click", function () {
    pageAction(url(urls.pageMove, currentPage.id) + "?direction=down");
  });

  document.getElementById("area-duplicate").addEventListener("click", function () {
    var a = selected();
    if (!a) return;
    flush().then(function () {
      post(url(urls.areaDuplicate, a.id), new FormData(), function (result) {
        book.pages = result.book.pages;
        currentPage = book.pages.filter(function (p) { return p.id === currentPage.id; })[0];
        selectedId = result.area;
        render();
      });
    });
  });

  // ------------------------------------------------------- the guide

  var guide = document.getElementById("guide-strip");
  var GUIDE_KEY = "tttool-guide-hidden";

  function updateGuide() {
    if (!guide || window.localStorage.getItem(GUIDE_KEY) === "1") return;
    var areas = book.pages.reduce(function (total, page) { return total + page.areas.length; }, 0);
    var withSound = book.pages.some(function (page) {
      return page.areas.some(function (a) { return a.sound_id || (a.sound_ids || []).length; });
    });
    var step = !currentPage.image ? "picture" : !areas ? "area" : !withSound ? "sound" : "build";
    guide.classList.remove("hidden");
    Array.prototype.forEach.call(guide.querySelectorAll("[data-step]"), function (item) {
      item.classList.toggle("now", item.dataset.step === step);
      item.classList.toggle("done", stepIndex(item.dataset.step) < stepIndex(step));
    });
  }

  function stepIndex(step) {
    return ["picture", "area", "sound", "build"].indexOf(step);
  }

  if (guide) {
    document.getElementById("guide-hide").addEventListener("click", function () {
      window.localStorage.setItem(GUIDE_KEY, "1");
      guide.classList.add("hidden");
    });
  }

  renderPages();
  showPicture();
  render();
  updateGuide();
})();
