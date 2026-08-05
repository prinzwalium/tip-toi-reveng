"use strict";

// ---------------------------------------------------------------- helpers

function $(selector, root) { return (root || document).querySelector(selector); }
function $$(selector, root) { return Array.from((root || document).querySelectorAll(selector)); }

// Confirmation for destructive forms (no inline handlers, keeps the CSP simple).
function wireConfirm() {
  $$("form[data-confirm]").forEach(function (form) {
    if (form.dataset.wired === "1") return;
    form.dataset.wired = "1";
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
}
wireConfirm();

// ------------------------------------------------------------- the editor

var editor = $("#editor");
if (editor) {
  editor.addEventListener("keydown", function (event) {
    if (event.key === "Tab") {
      event.preventDefault();
      var start = editor.selectionStart, end = editor.selectionEnd;
      editor.value = editor.value.slice(0, start) + "  " + editor.value.slice(end);
      editor.selectionStart = editor.selectionEnd = start + 2;
    }
    if ((event.ctrlKey || event.metaKey) && event.key === "s") {
      event.preventDefault();
      var stay = document.createElement("input");
      stay.type = "hidden"; stay.name = "stay"; stay.value = "1";
      editor.form.appendChild(stay);
      editor.form.submit();
    }
  });
}

// ------------------------------------------------------------ the command panel

var out = $("#output");
if (out) {
  var outText = $("#out-text");
  var outCommand = $("#out-command");
  var outStatus = $("#out-status");
  var outFiles = $("#out-files");
  var projectBase = window.location.pathname.replace(/\/$/, "");

  // Switching between commands
  $$(".tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      $$(".tab").forEach(function (t) { t.classList.toggle("active", t === tab); });
      $$(".cmdform").forEach(function (form) {
        form.classList.toggle("hidden", form.dataset.cmd !== tab.dataset.cmd);
      });
      var url = new URL(window.location.href);
      url.searchParams.set("cmd", tab.dataset.cmd);
      window.history.replaceState({}, "", url);
    });
  });

  // Pre-fill the output name from the chosen input file, e.g. book.yaml -> book.gme
  $$(".cmdform[data-derive]").forEach(function (form) {
    var parts = form.dataset.derive.split(":");
    var input = form.elements[parts[0]], output = form.elements[parts[1]], suffix = parts[2];
    if (!input || !output) return;
    input.addEventListener("change", function () {
      if (output.dataset.touched === "1" || !input.value) return;
      output.value = input.value.replace(/\.[^./]*$/, "") + suffix;
    });
    output.addEventListener("input", function () { output.dataset.touched = "1"; });
  });

  function setStatus(text, cls) {
    outStatus.textContent = text;
    outStatus.className = "badge " + (cls || "");
  }

  function renderFiles(files) {
    outFiles.innerHTML = "";
    ["created", "changed", "deleted"].forEach(function (kind) {
      var list = (files && files[kind]) || [];
      if (!list.length) return;
      var wrap = document.createElement("div");
      var tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = list.length + " " + kind;
      wrap.appendChild(tag);
      var ul = document.createElement("ul");
      list.slice(0, 200).forEach(function (path) {
        var li = document.createElement("li");
        if (kind === "deleted") {
          li.textContent = path;
        } else {
          var a = document.createElement("a");
          a.href = projectBase + "/download?path=" + encodeURIComponent(path);
          a.textContent = path;
          li.appendChild(a);
        }
        ul.appendChild(li);
      });
      if (list.length > 200) {
        var li = document.createElement("li");
        li.className = "muted";
        li.textContent = "… and " + (list.length - 200) + " more";
        ul.appendChild(li);
      }
      wrap.appendChild(ul);
      outFiles.appendChild(wrap);
    });
  }

  function showResult(result) {
    outCommand.textContent = result.command + (result.cwd && result.cwd !== "." ? "   (in " + result.cwd + "/)" : "");
    var duration = result.duration ? " · " + result.duration.toFixed(1) + "s" : "";
    if (result.ok) {
      setStatus("ok" + duration, "ok");
    } else {
      setStatus((result.exit_code === null ? "timeout" : "exit " + result.exit_code) + duration, "err");
    }
    outText.textContent = "";
    if (result.stdout) outText.appendChild(document.createTextNode(result.stdout));
    if (result.stderr) {
      var span = document.createElement("span");
      span.className = "stderr";
      span.textContent = (result.stdout ? "\n" : "") + result.stderr;
      outText.appendChild(span);
    }
    if (!result.stdout && !result.stderr) {
      outText.textContent = result.ok ? "(no output — that means success)" : "(no output)";
    }
    renderFiles(result.files);
    refreshFiles();
  }

  function showError(message) {
    setStatus("error", "err");
    outText.textContent = message;
    outFiles.innerHTML = "";
  }

  function refreshFiles() {
    fetch(projectBase + "/files", { headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        var target = $("#file-list");
        if (target) { target.innerHTML = html; wireFileActions(); }
      })
      .catch(function () { /* the page still works, just not live */ });
  }

  function submit(form, formData) {
    out.classList.remove("hidden");
    outCommand.textContent = "";
    outFiles.innerHTML = "";
    outText.textContent = "";
    setStatus("running…", "busy");
    fetch(form.action, {
      method: "POST",
      body: formData || new FormData(form),
      headers: { "X-Requested-With": "fetch", "Accept": "application/json" },
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (data.error) { showError(data.error); return; }
          showResult(data);
        });
      })
      .catch(function (err) { showError("Request failed: " + err); });
  }

  $$(".cmdform").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      submit(form);
      out.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  });

  $("#out-close").addEventListener("click", function () { out.classList.add("hidden"); });
  $("#out-download").addEventListener("click", function () {
    var blob = new Blob([outCommand.textContent + "\n\n" + outText.textContent], { type: "text/plain" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "tttool-output.txt";
    link.click();
    URL.revokeObjectURL(link.href);
  });

  // ---------------------------------------------------------- file actions

  var preview = $("#preview");
  var previewBody = $("#preview-body");
  var previewName = $("#preview-name");

  function closePreview() {
    preview.classList.add("hidden");
    previewBody.innerHTML = "";
  }
  $("#preview-close").addEventListener("click", closePreview);
  preview.addEventListener("click", function (event) { if (event.target === preview) closePreview(); });
  document.addEventListener("keydown", function (event) { if (event.key === "Escape") closePreview(); });

  function wireFileActions() {
    $$("[data-preview]").forEach(function (button) {
      button.addEventListener("click", function () {
        previewName.textContent = button.dataset.name;
        previewBody.innerHTML = "";
        var kind = button.dataset.kind;
        var node;
        if (kind === "image") {
          node = document.createElement("img");
          node.src = button.dataset.preview;
          node.alt = button.dataset.name;
        } else if (kind === "audio") {
          node = document.createElement("audio");
          node.controls = true;
          node.src = button.dataset.preview;
        } else {
          node = document.createElement("embed");
          node.src = button.dataset.preview;
          node.type = "application/pdf";
        }
        previewBody.appendChild(node);
        preview.classList.remove("hidden");
      });
    });

    $$("[data-convert]").forEach(function (button) {
      button.addEventListener("click", function () {
        var form = $("#convert-form");
        var data = new FormData();
        data.append("path", button.dataset.convert);
        var pseudo = { action: form.action };
        submit(pseudo, data);
      });
    });

    wireConfirm();
  }

  wireFileActions();
}
