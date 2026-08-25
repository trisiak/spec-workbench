/* Margin notes: build cards from the server's note data, pin them to their
   anchors Google-Docs style, and keep a single "focused" note that aligns
   exactly to its anchor while everything else stacks around it. After any
   mutation the page re-renders in place from /api/doc -- no reload, so the
   reader's scroll position and margin arrangement survive untouched. */
(function () {
  "use strict";

  var notes = JSON.parse(document.getElementById("notes-data").textContent);
  var doc = document.getElementById("doc");
  var railcol = document.getElementById("railcol");
  var article = document.getElementById("article");
  var twoCol = window.matchMedia("(min-width: 641px)");
  var focusedId = null;

  var TERMINAL_STATES = { resolved: true, accepted: true, rejected: true };

  /* which document this page shows; every API call carries it */
  var docName = new URLSearchParams(window.location.search).get("doc");
  function apiUrl(path) {
    return docName ? path + "?doc=" + encodeURIComponent(docName) : path;
  }

  // folded/unfolded choices survive a manual refresh (per document -- note
  // ids repeat across files)
  var FOLDS_KEY = "swb-folds:" + (docName || "default");
  var foldMemory;
  try {
    foldMemory = JSON.parse(sessionStorage.getItem(FOLDS_KEY) || "{}");
  } catch (e) {
    foldMemory = {};
  }

  function setFolded(wrapper, isFolded) {
    wrapper.classList.toggle("folded", isFolded);
    if (wrapper.dataset.id && wrapper.dataset.id !== "draft") {
      foldMemory[wrapper.dataset.id] = isFolded;
      sessionStorage.setItem(FOLDS_KEY, JSON.stringify(foldMemory));
    }
  }

  /* ---------- build note DOM ---------- */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function peekTextFor(note) {
    if (note.messages.length) {
      var tmp = el("div");
      tmp.innerHTML = note.messages[0].html;
      return tmp.textContent;
    }
    if (note.isDiff) return "suggested change";
    return note.bodyHtml ? "suggested replacement" : "";
  }

  function buildHead(note) {
    var head = el("div", "head");
    if (TERMINAL_STATES[note.state]) head.appendChild(el("span", "tick", "✓"));
    head.appendChild(el("span", "tid", "#" + note.id));
    if (note.anchor) head.appendChild(el("span", "", "on {#" + note.anchor + "}"));
    if (note.state === "open") {
      head.appendChild(el("span", "state-open", "open"));
    } else {
      var stateText = note.state + (note.stateDate ? " " + note.stateDate : "");
      head.appendChild(el("span", "state-terminal", stateText));
    }
    if (note.isNew) head.appendChild(el("span", "newmark", "new"));
    var fold = el("button", "fold");
    fold.setAttribute("aria-label", "Fold or unfold");
    fold.textContent = "[-]";
    head.appendChild(fold);
    return head;
  }

  function buildMessages(note, container) {
    note.messages.forEach(function (message) {
      var msg = el("div", "msg" + (message.isNew ? " fresh " + message.ink : ""));
      var who = el("span", "who " + message.ink, message.author);
      msg.appendChild(who);
      if (message.stamp) msg.appendChild(el("span", "when", message.stamp));
      if (message.isNew) msg.appendChild(el("span", "newmark", "new"));
      var body = el("div", "body");
      body.innerHTML = message.html;
      msg.appendChild(body);
      container.appendChild(msg);
    });
  }

  function buildSuggestionBody(note, container) {
    if (note.isDiff) {
      note.diffLines.forEach(function (line) {
        container.appendChild(el("div", "diffline " + line.op, line.text));
      });
    } else if (note.bodyHtml) {
      if (note.quote) {
        var quoteSpan = el("span", "sug-quote", '"' + note.quote + '" ');
        container.appendChild(quoteSpan);
      }
      var replacement = el("div", "sug-replacement");
      replacement.innerHTML = note.bodyHtml;
      container.appendChild(replacement);
    }
    if (note.author) {
      var msg = el("div", "msg");
      msg.appendChild(el("span", "who " + note.ink, note.author));
      if (note.authorDate) msg.appendChild(el("span", "when", note.authorDate));
      container.appendChild(msg);
    }
  }

  function buildActions(note, container) {
    var actions = el("div", "actions");
    var isOpenNow = note.state === "open";
    if (isOpenNow) {
      // replies belong to open notes; a resolved note must be reopened first
      var replyRow = el("div", "reply-row");
      var textarea = document.createElement("textarea");
      textarea.placeholder = "Reply…";
      textarea.setAttribute("aria-label", "Reply to #" + note.id);
      var replyBtn = el("button", "btn primary", "Reply");
      replyBtn.addEventListener("click", function () {
        submitReply(note.id, textarea);
      });
      textarea.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
          submitReply(note.id, textarea);
        }
      });
      attachAutogrow(textarea);
      replyRow.appendChild(textarea);
      replyRow.appendChild(replyBtn);
      container.appendChild(replyRow);
    }
    if (!isOpenNow) {
      var reopenBtn = el("button", "btn", "Reopen");
      reopenBtn.addEventListener("click", function () {
        postState(note.id, "open");
      });
      actions.appendChild(reopenBtn);
    } else if (note.isThread) {
      var resolveBtn = el("button", "btn", "Resolve");
      resolveBtn.addEventListener("click", function () {
        postState(note.id, "resolved");
      });
      actions.appendChild(resolveBtn);
    } else {
      var accept = el("button", "btn", "Accept");
      var reject = el("button", "btn", "Reject");
      accept.disabled = true;
      reject.disabled = true;
      accept.title = "arrives with suggestion mode (F2)";
      reject.title = "arrives with suggestion mode (F2)";
      actions.appendChild(accept);
      actions.appendChild(reject);
    }
    container.appendChild(actions);
  }

  function buildNote(note) {
    var wrapper = el("div", "note");
    wrapper.dataset.id = note.id;
    wrapper.dataset.anchor = note.anchor || "";
    wrapper.id = "note-" + note.id;
    var startsFolded = Object.prototype.hasOwnProperty.call(foldMemory, note.id)
      ? foldMemory[note.id]
      : Boolean(TERMINAL_STATES[note.state]);
    if (startsFolded) wrapper.classList.add("folded");

    var card = el("div", "card " + note.ink);
    card.appendChild(buildHead(note));
    card.appendChild(el("div", "peek", peekTextFor(note)));

    var bodyArea = el("div", "body-area");
    buildSuggestionBody(note, bodyArea);
    buildMessages(note, bodyArea);
    buildActions(note, bodyArea);
    card.appendChild(bodyArea);

    wrapper.appendChild(card);
    railcol.appendChild(wrapper);

    // interactions: whole header folds/unfolds, card body focuses, two-way hover
    card.querySelector(".head").addEventListener("click", function (event) {
      if (event.target.closest("button") && !event.target.closest(".fold")) return;
      event.stopPropagation();
      setFolded(wrapper, !wrapper.classList.contains("folded"));
      layoutRail();
    });
    card.addEventListener("click", function (event) {
      if (event.target.closest("button, textarea, a, .head")) return;
      focusNote(note.id, { fromLeft: false });
    });
    wrapper.addEventListener("mouseenter", function () { setHot(note.id, true); });
    wrapper.addEventListener("mouseleave", function () { setHot(note.id, false); });
  }

  /* ---------- anchor markers in the prose ---------- */

  function annotateAnchors() {
    // quote-anchored notes announce themselves through their underline;
    // only whole-block notes feed the count marker
    var notesByAnchor = {};
    notes.forEach(function (note) {
      if (!note.anchor || note.quote) return;
      (notesByAnchor[note.anchor] = notesByAnchor[note.anchor] || []).push(note);
    });
    Object.keys(notesByAnchor).forEach(function (anchorId) {
      var target = document.getElementById(anchorId);
      if (!target) return;
      var anchorNotes = notesByAnchor[anchorId];
      var openNotes = anchorNotes.filter(function (n) { return n.state === "open"; });
      var ink = (openNotes[0] || anchorNotes[0]).ink;
      target.classList.add("anch-h");
      target.dataset.notes = anchorNotes.map(function (n) { return n.id; }).join(" ");
      var count = el("span", "note-count " + ink, String(anchorNotes.length));
      count.title = anchorNotes.length + " note" + (anchorNotes.length > 1 ? "s" : "");
      target.appendChild(count);
      target.addEventListener("click", function () {
        var pick = openNotes[0] || anchorNotes[0];
        focusNote(pick.id, { fromLeft: true });
      });
      target.addEventListener("mouseenter", function () {
        anchorNotes.forEach(function (n) { setHot(n.id, true); });
      });
      target.addEventListener("mouseleave", function () {
        anchorNotes.forEach(function (n) { setHot(n.id, false); });
      });
    });
  }

  function setHot(noteId, isHot) {
    var wrapper = document.getElementById("note-" + noteId);
    if (wrapper) wrapper.classList.toggle("hot", isHot);
    document.querySelectorAll('.anch-q[data-note="' + noteId + '"]').forEach(function (span) {
      span.classList.toggle("hot", isHot);
    });
    notes.forEach(function (note) {
      if (note.id !== noteId || !note.anchor) return;
      var target = document.getElementById(note.anchor);
      if (target) target.classList.toggle("hot", isHot);
    });
  }

  /* ---------- phrase highlights: wrap each note's quote in its anchor block ---------- */

  function escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function wrapQuoteIn(rootEl, note) {
    var walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        return n.parentElement && n.parentElement.closest(".add-note, .note-count, .badge, .anch-q")
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT;
      },
    });
    var entries = [];
    var fullText = "";
    var node;
    while ((node = walker.nextNode())) {
      entries.push({ node: node, start: fullText.length });
      fullText += node.nodeValue;
    }
    var pattern = note.quote.trim().split(/\s+/).map(escapeRegExp).join("\\s+");
    var match = new RegExp(pattern).exec(fullText);
    if (!match) return false;
    var matchStart = match.index;
    var matchEnd = match.index + match[0].length;
    entries.forEach(function (entry) {
      var nodeStart = entry.start;
      var nodeEnd = entry.start + entry.node.nodeValue.length;
      var from = Math.max(nodeStart, matchStart);
      var to = Math.min(nodeEnd, matchEnd);
      if (from >= to) return;
      var range = document.createRange();
      range.setStart(entry.node, from - nodeStart);
      range.setEnd(entry.node, to - nodeStart);
      var span = document.createElement("span");
      span.className = "anch-q " + note.ink;
      span.dataset.note = note.id;
      range.surroundContents(span);
      span.addEventListener("click", function (event) {
        event.stopPropagation();
        focusNote(note.id, { fromLeft: true });
      });
      span.addEventListener("mouseenter", function () { setHot(note.id, true); });
      span.addEventListener("mouseleave", function () { setHot(note.id, false); });
    });
    return true;
  }

  function highlightQuotes() {
    notes.forEach(function (note) {
      if (!note.anchor || !note.quote) return;
      var target = document.getElementById(note.anchor);
      if (!target) return;
      note.hasQuoteSpan = wrapQuoteIn(target, note);
    });
  }

  /* ---------- focus state ---------- */

  function focusNote(noteId, options) {
    focusedId = noteId;
    document.querySelectorAll(".note.focused").forEach(function (n) {
      n.classList.remove("focused");
    });
    var wrapper = document.getElementById("note-" + noteId);
    if (!wrapper) return;
    wrapper.classList.add("focused");
    if (wrapper.classList.contains("folded")) setFolded(wrapper, false);
    layoutRail();
    // the note comes to the anchor -- never scroll the document out from
    // under the text being discussed. Only an explicit restore scrolls.
    if (options.scroll) {
      wrapper.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    if (options.fromLeft) {
      var textarea = wrapper.querySelector("textarea");
      if (textarea) textarea.focus({ preventScroll: true });
    }
  }

  function unfocus() {
    // a drafted comment survives losing focus -- only Cancel discards it
    focusedId = null;
    document.querySelectorAll(".note.focused").forEach(function (n) {
      n.classList.remove("focused");
    });
    layoutRail();
  }

  /* text boxes grow with their content */
  function attachAutogrow(textarea) {
    textarea.addEventListener("input", function () {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight, 180) + "px";
      layoutRail();
    });
  }

  /* ---------- new comments ---------- */

  function removeDraft() {
    var draft = railcol.querySelector(".note.draft");
    if (draft) draft.remove();
    // unwrap the while-drafting highlight
    document.querySelectorAll('.anch-q[data-note="draft"]').forEach(function (span) {
      while (span.firstChild) span.parentNode.insertBefore(span.firstChild, span);
      span.remove();
    });
  }

  function cleanHeadingText(heading) {
    var clone = heading.cloneNode(true);
    clone.querySelectorAll(".add-note, .note-count, .badge").forEach(function (n) { n.remove(); });
    return clone.textContent.trim();
  }

  /* an in-page ask -- the workspace embeds this app in a sandboxed frame
     where the browser suppresses window.confirm() without a trace */
  function askInPage(message, yesLabel, noLabel) {
    return new Promise(function (resolve) {
      var overlay = el("div", "ask-overlay");
      var card = el("div", "ask-card");
      card.appendChild(el("p", "ask-message", message));
      var buttons = el("div", "actions");
      var yesBtn = el("button", "btn primary", yesLabel);
      var noBtn = el("button", "btn", noLabel);
      buttons.appendChild(yesBtn);
      buttons.appendChild(noBtn);
      card.appendChild(buttons);
      overlay.appendChild(card);
      function finish(answer) {
        overlay.remove();
        document.removeEventListener("keydown", onKeydown, true);
        resolve(answer);
      }
      function onKeydown(event) {
        if (event.key === "Escape") {
          event.stopPropagation();
          finish(false);
        }
      }
      // the trailing click of a double-click arrives just after the dialog
      // opens -- wherever it lands, it must not silently answer for the user
      var openedAt = performance.now();
      function settled() {
        return performance.now() - openedAt > 300;
      }
      yesBtn.addEventListener("click", function () { if (settled()) finish(true); });
      noBtn.addEventListener("click", function () { if (settled()) finish(false); });
      overlay.addEventListener("click", function (event) {
        if (event.target === overlay && settled()) finish(false);
      });
      document.addEventListener("keydown", onKeydown, true);
      document.body.appendChild(overlay);
      noBtn.focus();
    });
  }

  function openDraft(target) {
    // an empty competing draft is discarded silently; a non-empty one asks
    // first, and declining returns you to it
    var existing = railcol.querySelector(".note.draft");
    if (existing) {
      var existingTextarea = existing.querySelector("textarea");
      if (existingTextarea.value.trim()) {
        askInPage(
          "Discard your other draft comment and start this one?",
          "Discard and start new",
          "Keep my draft"
        ).then(function (shouldDiscard) {
          if (shouldDiscard) {
            removeDraft();
            buildDraft(target);
          } else {
            // returning to the draft is an explicit choice, so bringing
            // it into view is the reader's own navigation
            existing.classList.add("focused");
            focusedId = "draft";
            layoutRail();
            existing.scrollIntoView({ block: "nearest", behavior: "smooth" });
            existingTextarea.focus({ preventScroll: true });
          }
        });
        return;
      }
      removeDraft();
    }
    buildDraft(target);
  }

  function buildDraft(target) {
    document.querySelectorAll(".note.focused").forEach(function (n) {
      n.classList.remove("focused");
    });

    var anchorLabel;
    if (target.quoteLabel) {
      anchorLabel = "on “" + target.quoteLabel + "”";
    } else if (target.anchorId) {
      anchorLabel = "on {#" + target.anchorId + "}";
    } else {
      anchorLabel = "on “" + target.headingText + "”";
    }
    var wrapper = el("div", "note draft focused");
    wrapper.dataset.id = "draft";
    wrapper.dataset.anchor = target.layoutAnchorId;
    var card = el("div", "card pen");
    var head = el("div", "head");
    head.appendChild(el("span", "tid", "new comment"));
    head.appendChild(el("span", "", anchorLabel));
    card.appendChild(head);

    var bodyArea = el("div", "body-area");
    var replyRow = el("div", "reply-row");
    var textarea = document.createElement("textarea");
    textarea.placeholder = "Comment…";
    textarea.setAttribute("aria-label", "New comment " + anchorLabel);
    attachAutogrow(textarea);
    replyRow.appendChild(textarea);
    bodyArea.appendChild(replyRow);

    var actions = el("div", "actions");
    var submitBtn = el("button", "btn primary", "Comment");
    var cancelBtn = el("button", "btn", "Cancel");
    submitBtn.addEventListener("click", function () { submitDraft(target, textarea); });
    cancelBtn.addEventListener("click", function () {
      removeDraft();
      unfocus();
    });
    textarea.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        submitDraft(target, textarea);
      }
    });
    actions.appendChild(submitBtn);
    actions.appendChild(cancelBtn);
    bodyArea.appendChild(actions);
    card.appendChild(bodyArea);
    wrapper.appendChild(card);
    railcol.appendChild(wrapper);

    // highlight the words under discussion while the draft is alive
    if (target.quote) {
      var quoteBlock = document.getElementById(target.layoutAnchorId);
      if (quoteBlock) {
        wrapQuoteIn(quoteBlock, { quote: target.quote, ink: "pen", id: "draft" });
      }
    }

    focusedId = "draft";
    layoutRail();
    wrapper.scrollIntoView({ block: "nearest", behavior: "smooth" });
    // focus again after the click/selection teardown settles -- a single
    // immediate focus() loses to the browser's selection handling. In a
    // nested frame the frame itself may not hold focus, and without it the
    // caret never renders -- claim it first.
    function focusDraftBox() {
      window.focus();
      textarea.focus({ preventScroll: true });
    }
    focusDraftBox();
    setTimeout(focusDraftBox, 200);
  }

  function submitDraft(target, textarea) {
    var text = textarea.value.trim();
    if (!text) return;
    var payload;
    if (target.quote) {
      payload = {
        sline: parseInt(target.sline, 10),
        eline: parseInt(target.eline, 10),
        prefix: target.prefix,
        quote: target.quote,
        before: target.before,
        after: target.after,
        text: text,
      };
    } else if (target.anchorId) {
      payload = { anchor: target.anchorId, text: text };
    } else {
      payload = { heading: target.headingText, text: text };
    }
    fetch(apiUrl("api/notes"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (response) {
      if (response.ok) {
        response.json().then(function (data) { refreshDocument(data.id); });
      } else {
        response.json().then(function (data) { showToast(data.error || "Comment failed"); });
      }
    });
  }

  /* ---------- select text to comment on exactly those words ---------- */

  var selectionButton = null;
  var pendingSelection = null;
  var tempSelectionIdCounter = 0;

  function closestBlockOf(container) {
    var element = container.nodeType === Node.TEXT_NODE ? container.parentElement : container;
    return element ? element.closest("[data-sline]") : null;
  }

  function hideSelectionButton() {
    if (selectionButton) selectionButton.style.display = "none";
    pendingSelection = null;
  }

  function handleTextSelection() {
    var selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) { hideSelectionButton(); return; }
    var range = selection.getRangeAt(0);
    var startBlock = closestBlockOf(range.startContainer);
    var endBlock = closestBlockOf(range.endContainer);
    if (!startBlock || startBlock !== endBlock || !article.contains(startBlock)) {
      hideSelectionButton();
      return;
    }
    var quote = selection.toString().trim();
    if (!quote) { hideSelectionButton(); return; }

    // the selection's real neighborhood, for server-side disambiguation
    var beforeRange = document.createRange();
    beforeRange.selectNodeContents(startBlock);
    beforeRange.setEnd(range.startContainer, range.startOffset);
    var afterRange = document.createRange();
    afterRange.selectNodeContents(startBlock);
    afterRange.setStart(range.endContainer, range.endOffset);
    pendingSelection = {
      block: startBlock,
      quote: quote,
      before: beforeRange.toString().slice(-120),
      after: afterRange.toString().slice(0, 120),
    };

    var rect = range.getBoundingClientRect();
    selectionButton.style.display = "block";
    selectionButton.style.left = Math.round(rect.right + window.scrollX + 6) + "px";
    selectionButton.style.top = Math.round(rect.bottom + window.scrollY + 4) + "px";
  }

  function openDraftFromSelection() {
    if (!pendingSelection) return;
    var block = pendingSelection.block;
    if (!block.id) {
      tempSelectionIdCounter += 1;
      block.id = "tmp--sel-" + tempSelectionIdCounter;
    }
    var clone = block.cloneNode(true);
    clone.querySelectorAll(".add-note, .note-count, .badge").forEach(function (n) { n.remove(); });
    var shortQuote = pendingSelection.quote.length > 40
      ? pendingSelection.quote.slice(0, 40) + "…"
      : pendingSelection.quote;
    var draftQuote = pendingSelection.quote;
    openDraft({
      anchorId: null,
      headingText: null,
      sline: block.dataset.sline,
      eline: block.dataset.eline,
      prefix: clone.textContent.trim().slice(0, 120),
      quote: draftQuote,
      before: pendingSelection.before,
      after: pendingSelection.after,
      quoteLabel: shortQuote,
      layoutAnchorId: block.id,
    });
    hideSelectionButton();
    window.getSelection().removeAllRanges();
  }

  function installSelectionButton() {
    selectionButton = el("button", "btn primary sel-comment", "Comment");
    selectionButton.style.display = "none";
    document.body.appendChild(selectionButton);
    // no mousedown preventDefault here: pendingSelection already holds the
    // captured quote, and the default lets the click give this (possibly
    // unfocused, nested) frame real focus so the caret can land in the box
    selectionButton.addEventListener("click", openDraftFromSelection);
    article.addEventListener("mouseup", function () {
      setTimeout(handleTextSelection, 10);
    });
    document.addEventListener("mousedown", function (event) {
      if (event.target !== selectionButton) hideSelectionButton();
    });
  }

  function addCommentAffordances() {
    // every heading is commentable; anchor-less ones get their id minted
    // by the server the first time a comment lands on them
    var headings = article.querySelectorAll("h1, h2, h3, h4, h5, h6");
    var tempIdCounter = 0;
    headings.forEach(function (heading) {
      var target;
      if (heading.id) {
        target = { anchorId: heading.id, headingText: null, layoutAnchorId: heading.id };
      } else {
        tempIdCounter += 1;
        heading.id = "tmp--heading-" + tempIdCounter;
        target = {
          anchorId: null,
          headingText: cleanHeadingText(heading),
          layoutAnchorId: heading.id,
        };
      }
      var plus = el("span", "add-note", "+");
      plus.title = "New comment";
      plus.setAttribute("role", "button");
      plus.tabIndex = 0;
      plus.addEventListener("click", function (event) {
        event.stopPropagation();
        openDraft(target);
      });
      plus.addEventListener("keydown", function (event) {
        if (event.key === "Enter") openDraft(target);
      });
      heading.appendChild(plus);
    });
  }

  document.addEventListener("keydown", function (event) {
    if ((event.metaKey || event.ctrlKey) && (event.key === "f" || event.key === "F")) {
      event.preventDefault();
      openSearch();
      return;
    }
    if (event.key === "Escape") unfocus();
  });
  article.addEventListener("click", function (event) {
    if (!event.target.closest(".anch-h")) unfocus();
  });

  /* ---------- rail layout: pin to anchors, focused note wins its spot ---------- */

  function anchorYFor(wrapper) {
    // a phrase-anchored note pins to its highlighted words, not the whole block
    var quoteSpan = wrapper.dataset.id
      ? document.querySelector('.anch-q[data-note="' + wrapper.dataset.id + '"]')
      : null;
    var anchorId = wrapper.dataset.anchor;
    var target = quoteSpan || (anchorId ? document.getElementById(anchorId) : null);
    if (!target) return 0;
    return target.getBoundingClientRect().top - doc.getBoundingClientRect().top - 36;
  }

  function layoutRail() {
    var wrappers = Array.prototype.slice.call(railcol.querySelectorAll(".note"));
    if (!twoCol.matches) {
      wrappers.forEach(function (w) { w.style.top = ""; });
      railcol.style.minHeight = "";
      return;
    }
    var entries = wrappers.map(function (w) {
      return { wrapper: w, want: anchorYFor(w) };
    });
    entries.sort(function (a, b) { return a.want - b.want; });

    var focusedIdx = entries.findIndex(function (e) {
      return e.wrapper.dataset.id === focusedId;
    });

    var GAP = 12;
    if (focusedIdx >= 0) {
      // the focused note sits exactly at its anchor; neighbors yield
      var focused = entries[focusedIdx];
      focused.top = focused.want;
      for (var i = focusedIdx - 1; i >= 0; i--) {
        var below = entries[i + 1];
        var maxTop = below.top - GAP - entries[i].wrapper.offsetHeight;
        entries[i].top = Math.min(entries[i].want, maxTop);
      }
      for (var j = focusedIdx + 1; j < entries.length; j++) {
        var above = entries[j - 1];
        var minTop = above.top + above.wrapper.offsetHeight + GAP;
        entries[j].top = Math.max(entries[j].want, minTop);
      }
    } else {
      var prevBottom = -GAP;
      entries.forEach(function (entry) {
        entry.top = Math.max(entry.want, prevBottom + GAP);
        prevBottom = entry.top + entry.wrapper.offsetHeight;
      });
    }

    var maxBottom = 0;
    entries.forEach(function (entry) {
      entry.wrapper.style.top = Math.max(0, entry.top) + "px";
      maxBottom = Math.max(maxBottom, entry.top + entry.wrapper.offsetHeight);
    });
    railcol.style.minHeight = maxBottom + 20 + "px";
  }

  /* ---------- server actions ---------- */

  function showToast(text) {
    var toast = document.getElementById("toast");
    toast.textContent = text;
    toast.classList.add("shown");
    setTimeout(function () { toast.classList.remove("shown"); }, 2200);
  }

  function setHeaderField(elementId, text) {
    var field = document.getElementById(elementId);
    if (!field) return;
    field.textContent = text || "";
    field.hidden = !text;
    delete field.dataset.full;
  }

  /* header stamps read as relative time; the precise stamp lives in the tooltip */

  function relativeTime(isoString) {
    var then = Date.parse(isoString);
    if (isNaN(then)) return isoString;
    var seconds = Math.round((Date.now() - then) / 1000);
    if (seconds < 45) return "just now";
    if (seconds < 90) return "1m ago";
    var minutes = Math.round(seconds / 60);
    if (minutes < 60) return minutes + "m ago";
    var hours = Math.round(minutes / 60);
    if (hours < 24) return hours + "h ago";
    return Math.round(hours / 24) + "d ago";
  }

  var ISO_IN_TEXT_RE = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z/;

  function humanizeHeaderTimes() {
    ["agentseen", "notified"].forEach(function (elementId) {
      var field = document.getElementById(elementId);
      if (!field || field.hidden) return;
      var full = field.dataset.full || field.textContent;
      var match = full.match(ISO_IN_TEXT_RE);
      if (!match) return;
      field.dataset.full = full;
      // an in-app tooltip (styled ::after) -- native title tips are laggy
      // and unreliable inside the sandboxed frame
      field.dataset.tip = full;
      field.textContent = full.replace(match[0], relativeTime(match[0]));
    });
  }

  function applyDocument(data) {
    // re-render prose and rail in place from fresh server state; the
    // scroll position is simply never touched
    notes = data.notes;
    article.innerHTML = data.articleHtml;
    railcol.innerHTML = "";
    setHeaderField("docstatus", data.docStatus);
    setHeaderField("agentseen", data.agentSeen ? "agent-seen " + data.agentSeen : "");
    setHeaderField("notified", data.notified ? "notified " + data.notified : "");
    var newNav = document.getElementById("newnav");
    if (newNav) {
      document.getElementById("newlabel").textContent =
        data.newForYou ? data.newForYou + " new for you" : "";
      newNav.hidden = !data.newForYou;
    }
    var notifyBtn = document.getElementById("notify");
    if (notifyBtn) {
      notifyBtn.textContent = "notify agent" + (data.pendingCount ? " (" + data.pendingCount + ")" : "");
    }
    var notifySplit = document.getElementById("notifysplit");
    if (notifySplit) notifySplit.dataset.agent = data.notifyAgent || "";
    var agentNames = document.getElementById("agentnames");
    if (agentNames) agentNames.textContent = data.agentNames || "agent";
    // our own re-render consumed this change; the poll shouldn't re-fire
    // on it, and any pending stale notice is satisfied by it
    if (data.docStamp) lastDocStamp = data.docStamp;
    if (stalePill) stalePill.hidden = true;
    humanizeHeaderTimes();
    buildAll();
    // the re-render killed any live ranges; re-run an open search on the new DOM
    if (searchBar && !searchBar.hidden) runSearch();
  }

  function buildAll() {
    notes.forEach(buildNote);
    annotateAnchors();
    addCommentAffordances();
    highlightQuotes();
    layoutRail();
  }

  function refreshDocument(focusId) {
    fetch(apiUrl("api/doc")).then(function (response) {
      if (!response.ok) {
        showToast("Refresh failed -- reload the page");
        return;
      }
      response.json().then(function (data) {
        applyDocument(data);
        if (focusId) focusNote(focusId, { fromLeft: false, scroll: false });
      });
    });
  }

  /* stale-view notice (#t34): poll the document's on-disk stamp and, when
     the file changes under us (an agent's sweep, a hand edit), show a
     quiet click-to-refresh pill. NOTHING re-renders on its own -- a page
     mid-read or mid-comment never moves; the click applies the same
     no-reload path replies use, so scroll and folds survive. */
  var lastDocStamp = null;
  var stalePill = null;
  function showStalePill() {
    if (!stalePill) {
      stalePill = el("button", "stale-pill", "document changed — refresh");
      stalePill.addEventListener("click", function () {
        stalePill.hidden = true;
        refreshDocument(null);
      });
      document.body.appendChild(stalePill);
    }
    stalePill.hidden = false;
  }
  function pollDocStamp() {
    if (document.visibilityState === "hidden") return;
    fetch(apiUrl("api/stamp")).then(function (response) {
      if (!response.ok) return;
      response.json().then(function (data) {
        if (lastDocStamp === null) { lastDocStamp = data.stamp; return; }
        if (data.stamp !== lastDocStamp) showStalePill();
      });
    }).catch(function () {});
  }
  setInterval(pollDocStamp, 4000);
  pollDocStamp();

  function submitReply(noteId, textarea) {
    var text = textarea.value.trim();
    if (!text) return;
    fetch(apiUrl("api/notes/" + noteId + "/reply"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text }),
    }).then(function (response) {
      if (response.ok) { refreshDocument(noteId); }
      else { response.json().then(function (data) { showToast(data.error || "Reply failed"); }); }
    });
  }

  function postState(noteId, state) {
    fetch(apiUrl("api/notes/" + noteId + "/state"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state: state }),
    }).then(function (response) {
      if (!response.ok) {
        response.json().then(function (data) { showToast(data.error || "Update failed"); });
        return;
      }
      if (state === "open") {
        refreshDocument(noteId);
      } else {
        // resolving closes the note in the same click: drop any remembered
        // unfold so the terminal default folds it, and let focus go
        delete foldMemory[noteId];
        sessionStorage.setItem(FOLDS_KEY, JSON.stringify(foldMemory));
        focusedId = null;
        refreshDocument(null);
      }
    });
  }

  /* ---------- notify agent ---------- */

  function notifyAgent(message) {
    fetch(apiUrl("api/notify"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message || "" }),
    }).then(function (response) {
      if (!response.ok) {
        response.json().then(function (data) { showToast(data.error || "Notify failed"); });
        return;
      }
      response.json().then(function (data) {
        showToast("agent notified (v" + data.version + ")");
        refreshDocument(null);
      });
    });
  }

  /* ---------- in-document search (Cmd/Ctrl+F) ---------- */

  var searchBar = null;
  var searchInput = null;
  var searchCount = null;
  var searchInComments = null;
  var searchMatches = [];
  var searchIndex = -1;

  function buildSearchBar() {
    searchBar = el("div", "searchbar");
    searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = "Find…";
    searchInput.className = "search-input";
    searchInput.setAttribute("aria-label", "Find in document");
    var scopeLabel = el("label", "search-scope");
    searchInComments = document.createElement("input");
    searchInComments.type = "checkbox";
    scopeLabel.appendChild(searchInComments);
    scopeLabel.appendChild(document.createTextNode(" in comments"));
    searchCount = el("span", "search-count", "");
    var prevBtn = el("button", "btn", "▲");
    var nextBtn = el("button", "btn", "▼");
    var closeBtn = el("button", "btn", "×");
    prevBtn.title = "Previous match (Shift+Enter)";
    nextBtn.title = "Next match (Enter)";
    closeBtn.title = "Close (Esc)";
    [searchInput, scopeLabel, searchCount, prevBtn, nextBtn, closeBtn].forEach(function (n) {
      searchBar.appendChild(n);
    });
    searchBar.hidden = true;
    document.body.appendChild(searchBar);
    searchInput.addEventListener("input", runSearch);
    searchInComments.addEventListener("change", runSearch);
    prevBtn.addEventListener("click", function () { stepSearch(-1); });
    nextBtn.addEventListener("click", function () { stepSearch(1); });
    closeBtn.addEventListener("click", closeSearch);
    searchInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        stepSearch(event.shiftKey ? -1 : 1);
      } else if (event.key === "Escape") {
        event.stopPropagation();
        closeSearch();
      }
    });
  }

  function openSearch() {
    searchBar.hidden = false;
    searchInput.focus();
    searchInput.select();
    runSearch();
  }

  function closeSearch() {
    searchBar.hidden = true;
    clearSearchHighlights();
    searchMatches = [];
    searchIndex = -1;
    searchCount.textContent = "";
  }

  function clearSearchHighlights() {
    if (window.CSS && CSS.highlights) {
      CSS.highlights.delete("swb-search");
      CSS.highlights.delete("swb-search-current");
    }
  }

  function collectSearchRanges(needle) {
    // plain-text matches within single text nodes; .peek duplicates a
    // note's first message, so it is excluded
    var roots = [article];
    if (searchInComments.checked) roots.push(railcol);
    var ranges = [];
    roots.forEach(function (root) {
      var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: function (n) {
          return n.parentElement && n.parentElement.closest(".peek")
            ? NodeFilter.FILTER_REJECT
            : NodeFilter.FILTER_ACCEPT;
        },
      });
      var node;
      while ((node = walker.nextNode())) {
        var haystack = node.nodeValue.toLowerCase();
        var from = 0;
        var at;
        while ((at = haystack.indexOf(needle, from)) !== -1) {
          var range = document.createRange();
          range.setStart(node, at);
          range.setEnd(node, at + needle.length);
          ranges.push(range);
          from = at + needle.length;
        }
      }
    });
    return ranges;
  }

  function runSearch() {
    clearSearchHighlights();
    searchMatches = [];
    searchIndex = -1;
    var query = searchInput.value.trim().toLowerCase();
    if (!query) {
      searchCount.textContent = "";
      return;
    }
    searchMatches = collectSearchRanges(query);
    if (!searchMatches.length) {
      searchCount.textContent = "0 matches";
      return;
    }
    stepSearch(1);
  }

  function stepSearch(step) {
    if (!searchMatches.length) return;
    searchIndex = ((searchIndex + step) % searchMatches.length + searchMatches.length) % searchMatches.length;
    var current = searchMatches[searchIndex];
    searchCount.textContent = (searchIndex + 1) + "/" + searchMatches.length;
    // a match hidden inside a folded note unfolds it
    var container = current.startContainer.parentElement;
    var wrapper = container ? container.closest(".note") : null;
    if (wrapper && wrapper.classList.contains("folded")) {
      setFolded(wrapper, false);
      layoutRail();
    }
    if (window.CSS && CSS.highlights) {
      CSS.highlights.set("swb-search", new Highlight());
      searchMatches.forEach(function (range) { CSS.highlights.get("swb-search").add(range); });
      CSS.highlights.set("swb-search-current", new Highlight(current));
    }
    var rect = current.getBoundingClientRect();
    window.scrollTo({
      top: window.scrollY + rect.top - window.innerHeight / 3,
      behavior: "smooth",
    });
  }

  /* the chevron half of the split button: notify with a message riding along */
  var notifyPop = null;
  var notifyPopText = null;
  var notifyPopWho = null;
  function notifyTargetName() {
    var split = document.getElementById("notifysplit");
    return (split && split.dataset.agent) || "";
  }
  function toggleNotifyPopover() {
    if (!notifyPop) {
      notifyPop = el("div", "notify-pop");
      notifyPopText = document.createElement("textarea");
      notifyPopText.setAttribute("aria-label", "Message to send with the notification");
      // button left-aligned like the comment box; who-it-reaches to its right (#t32)
      var actions = el("div", "actions");
      var sendBtn = el("button", "btn primary", "Notify");
      notifyPopWho = el("span", "who");
      actions.appendChild(sendBtn);
      actions.appendChild(notifyPopWho);
      notifyPop.appendChild(notifyPopText);
      notifyPop.appendChild(actions);
      notifyPop.hidden = true;
      document.body.appendChild(notifyPop);
      sendBtn.addEventListener("click", function () {
        notifyPop.hidden = true;
        notifyAgent(notifyPopText.value.trim());
      });
      notifyPopText.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) sendBtn.click();
        if (event.key === "Escape") {
          event.stopPropagation();
          notifyPop.hidden = true;
        }
      });
      document.addEventListener("mousedown", function (event) {
        if (!notifyPop.hidden && !notifyPop.contains(event.target) && event.target.id !== "notifychev") {
          notifyPop.hidden = true;
        }
      });
    }
    if (notifyPop.hidden) {
      var target = notifyTargetName();
      notifyPopWho.textContent = target ? "will message " + target : "no agent set for this document";
      notifyPopText.value = "Please sweep the document.";
      notifyPop.hidden = false;
      notifyPopText.focus();
      notifyPopText.select();
    } else {
      notifyPop.hidden = true;
    }
  }

  /* jump between new items: label advances, arrows go either way */
  var newNavCursor = -1;
  function jumpToNewItem(step) {
    var targets = notes
      .filter(function (n) { return n.isNew; })
      .map(function (n) { return document.getElementById("note-" + n.id); })
      .filter(Boolean)
      .sort(function (a, b) { return a.offsetTop - b.offsetTop; });
    if (!targets.length) return;
    newNavCursor = ((newNavCursor + step) % targets.length + targets.length) % targets.length;
    focusNote(targets[newNavCursor].dataset.id, { fromLeft: false, scroll: true });
  }

  /* ---------- open another file ---------- */

  function openFilePicker() {
    fetch("api/files").then(function (response) {
      return response.json();
    }).then(function (data) {
      var overlay = el("div", "ask-overlay");
      var card = el("div", "ask-card file-pick");
      card.appendChild(el("p", "ask-message", "Open a markdown file"));
      var filter = document.createElement("input");
      filter.type = "text";
      filter.placeholder = "Filter…";
      filter.className = "file-filter";
      card.appendChild(filter);
      var list = el("div", "file-list");
      card.appendChild(list);
      overlay.appendChild(card);

      function close() {
        overlay.remove();
        document.removeEventListener("keydown", onKeydown, true);
      }
      function openFile(path) {
        window.location.href = "?doc=" + encodeURIComponent(path);
      }
      function visibleRows() {
        return Array.prototype.slice.call(list.querySelectorAll(".file-row"))
          .filter(function (row) { return !row.hidden; });
      }
      function onKeydown(event) {
        if (event.key === "Escape") {
          event.stopPropagation();
          close();
        } else if (event.key === "Enter" && document.activeElement === filter) {
          var rows = visibleRows();
          if (rows.length) openFile(rows[0].dataset.path);
        }
      }
      data.files.forEach(function (path) {
        var row = el("button", "file-row", path);
        row.dataset.path = path;
        if (path === (docName || document.querySelector("header .path").textContent)) {
          row.classList.add("current");
        }
        row.addEventListener("click", function () { openFile(path); });
        list.appendChild(row);
      });
      filter.addEventListener("input", function () {
        var needle = filter.value.trim().toLowerCase();
        list.querySelectorAll(".file-row").forEach(function (row) {
          row.hidden = needle !== "" && row.dataset.path.toLowerCase().indexOf(needle) === -1;
        });
      });
      overlay.addEventListener("click", function (event) {
        if (event.target === overlay) close();
      });
      document.addEventListener("keydown", onKeydown, true);
      document.body.appendChild(overlay);
      filter.focus();
    });
  }

  /* ---------- boot ---------- */

  var toast = el("div", "toast");
  toast.id = "toast";
  document.body.appendChild(toast);

  buildAll();
  installSelectionButton();
  buildSearchBar();

  var openFileButton = document.getElementById("openfile");
  if (openFileButton) openFileButton.addEventListener("click", openFilePicker);
  var notifyButton = document.getElementById("notify");
  if (notifyButton) notifyButton.addEventListener("click", function () { notifyAgent(""); });
  var notifyChevron = document.getElementById("notifychev");
  if (notifyChevron) notifyChevron.addEventListener("click", toggleNotifyPopover);
  var newLabelButton = document.getElementById("newlabel");
  var newPrevButton = document.getElementById("newprev");
  var newNextButton = document.getElementById("newnext");
  if (newLabelButton) newLabelButton.addEventListener("click", function () { jumpToNewItem(1); });
  if (newNextButton) newNextButton.addEventListener("click", function () { jumpToNewItem(1); });
  if (newPrevButton) newPrevButton.addEventListener("click", function () { jumpToNewItem(-1); });

  humanizeHeaderTimes();
  setInterval(humanizeHeaderTimes, 60000);

  window.addEventListener("resize", layoutRail);
  // fonts settle after DOM-ready and shift every anchor's pixel position
  window.addEventListener("load", layoutRail);
})();
