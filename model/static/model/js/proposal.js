document.addEventListener("DOMContentLoaded", () => {
  const getCsrfToken = () => {
    const cookie = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="));

    return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
  };

  // -------------------------------------------------------------
  // "+ New proposal" -- lives in the sidebar, which renders on every
  // model page (and can be replaced wholesale after a proposal-
  // editing AJAX save, see model_editing.js's `postForm`), so this
  // is delegated to `document` rather than bound to the button
  // directly, and wired up unconditionally (not gated behind the
  // .model-proposal guard below).
  // -------------------------------------------------------------

  document.addEventListener("click", async (event) => {
    const newProposalBtn = event.target.closest("#model-new-proposal-btn");

    if (!newProposalBtn) {
      return;
    }

    newProposalBtn.disabled = true;

    try {
      const response = await fetch(newProposalBtn.dataset.createUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCsrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
      });

      const data = await response.json();

      if (data.success) {
        window.location.href = data.redirect_url;
      } else {
        window.alert(data.error || "Could not create a new proposal.");
        newProposalBtn.disabled = false;
      }
    } catch (error) {
      console.error("New proposal failed:", error);
      window.alert("Could not create a new proposal. Please try again.");
      newProposalBtn.disabled = false;
    }
  });

  const proposal = document.querySelector(".model-proposal");

  if (!proposal) {
    return;
  }

  const postAction = async (action, changeId = null, extraFields = null) => {
    const formData = new FormData();

    formData.append("action", action);

    if (changeId) {
      formData.append("change_id", changeId);
    }

    if (extraFields) {
      Object.entries(extraFields).forEach(([key, value]) => {
        formData.append(key, value);
      });
    }

    const response = await fetch(window.location.href, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    return response;
  };

  const setButtonsDisabled = (disabled) => {
    proposal.querySelectorAll("button").forEach((button) => {
      button.disabled = disabled;
    });
  };

  const runAction = async (action, changeId = null, extraFields = null) => {
    setButtonsDisabled(true);

    try {
      const response = await postAction(action, changeId, extraFields);
      const data = await response.json().catch(() => ({}));

      if (data.redirect_url) {
        window.location.href = data.redirect_url;
      } else {
        window.location.reload();
      }
    } catch (error) {
      console.error("Proposal action failed:", error);
      setButtonsDisabled(false);
      window.alert("The change could not be updated. Please try again.");
    }
  };

  proposal.querySelectorAll(".model-proposal-review").forEach((button) => {
    button.addEventListener("click", () => {
      runAction("review", button.dataset.changeId);
    });
  });

  proposal.querySelectorAll(".model-proposal-unreview").forEach((button) => {
    button.addEventListener("click", () => {
      runAction("unreview", button.dataset.changeId);
    });
  });

  const closeDiscardConfirm = (actionsContainer) => {
    actionsContainer.classList.remove("is-confirming");
  };

  const openDiscardConfirm = (actionsContainer) => {
    proposal
      .querySelectorAll(".model-proposal-change-actions.is-confirming")
      .forEach((container) => {
        if (container !== actionsContainer) {
          closeDiscardConfirm(container);
        }
      });

    actionsContainer.classList.add("is-confirming");
  };

  proposal.querySelectorAll(".model-proposal-discard").forEach((button) => {
    const actionsContainer = button.closest(".model-proposal-change-actions");

    button.addEventListener("click", () => {
      openDiscardConfirm(actionsContainer);
    });
  });

  proposal
    .querySelectorAll(".model-proposal-discard-confirm-no")
    .forEach((button) => {
      const actionsContainer = button.closest(".model-proposal-change-actions");

      button.addEventListener("click", () => {
        closeDiscardConfirm(actionsContainer);
      });
    });

  proposal
    .querySelectorAll(".model-proposal-discard-confirm-yes")
    .forEach((button) => {
      const actionsContainer = button.closest(".model-proposal-change-actions");

      button.addEventListener("click", () => {
        runAction("discard", actionsContainer.dataset.changeId);
      });
    });

  const reviewAllButton = proposal.querySelector(".model-proposal-review-all");

  if (reviewAllButton) {
    reviewAllButton.addEventListener("click", () => {
      runAction("review_all");
    });
  }

  const unreviewAllButton = proposal.querySelector(
    ".model-proposal-unreview-all",
  );

  if (unreviewAllButton) {
    unreviewAllButton.addEventListener("click", () => {
      runAction("unreview_all");
    });
  }

  // -------------------------------------------------------------
  // Evidence references (per change). Unlike the actions above these
  // do not reload the page: a proposal can hold many changes, so the
  // affected change's evidence block is swapped in place with the
  // server-rendered fragment. Listeners are delegated because that
  // block is replaced after every save.
  // -------------------------------------------------------------

  const changesContainer = proposal.querySelector(".model-proposal-changes");

  const evidencePost = async (fields) => {
    const formData = new FormData();

    Object.entries(fields).forEach(([key, value]) => {
      formData.append(key, value);
    });

    const response = await fetch(window.location.href, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: formData,
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok || !data.success) {
      throw new Error(data.error || "The evidence could not be saved.");
    }

    return data;
  };

  const replaceEvidenceBlock = (block, html) => {
    const template = document.createElement("template");
    template.innerHTML = html.trim();
    block.replaceWith(template.content.firstElementChild);
  };

  const closeEvidenceForm = (block) => {
    const form = block.querySelector(".model-proposal-evidence-form");

    form.hidden = true;
    form.reset();
    delete form.dataset.evidenceId;
    form.querySelector(".model-proposal-evidence-error").textContent = "";
  };

  const openEvidenceForm = (block, item = null) => {
    // One open form at a time keeps a long proposal tidy.
    changesContainer
      .querySelectorAll(".model-proposal-evidence-form:not([hidden])")
      .forEach((openForm) => {
        closeEvidenceForm(openForm.closest(".model-proposal-evidence"));
      });

    const form = block.querySelector(".model-proposal-evidence-form");

    form.elements.source.value = item ? item.dataset.source : "";
    form.elements.locator.value = item ? item.dataset.locator : "";
    form.elements.note.value = item ? item.dataset.note : "";

    if (item) {
      form.dataset.evidenceId = item.dataset.evidenceId;
    } else {
      delete form.dataset.evidenceId;
    }

    form.hidden = false;
    form.elements.source.focus();
  };

  if (changesContainer) {
    changesContainer.addEventListener("click", async (event) => {
      const target = event.target.closest("button");

      if (!target) {
        return;
      }

      const block = target.closest(".model-proposal-evidence");

      if (!block) {
        return;
      }

      const item = target.closest(".model-proposal-evidence-item");

      if (target.classList.contains("model-proposal-evidence-add")) {
        openEvidenceForm(block);
      } else if (target.classList.contains("model-proposal-evidence-edit")) {
        openEvidenceForm(block, item);
      } else if (target.classList.contains("model-proposal-evidence-cancel")) {
        closeEvidenceForm(block);
      } else if (target.classList.contains("model-proposal-evidence-remove")) {
        item.classList.add("is-confirming");
      } else if (
        target.classList.contains("model-proposal-evidence-confirm-no")
      ) {
        item.classList.remove("is-confirming");
      } else if (
        target.classList.contains("model-proposal-evidence-confirm-yes")
      ) {
        target.disabled = true;

        try {
          const data = await evidencePost({
            action: "remove_evidence",
            evidence_id: item.dataset.evidenceId,
          });

          replaceEvidenceBlock(block, data.html);
        } catch (error) {
          console.error("Removing evidence failed:", error);
          target.disabled = false;
          item.classList.remove("is-confirming");
          window.alert(error.message);
        }
      }
    });

    changesContainer.addEventListener("submit", async (event) => {
      const form = event.target.closest(".model-proposal-evidence-form");

      if (!form) {
        return;
      }

      event.preventDefault();

      const block = form.closest(".model-proposal-evidence");
      const errorEl = form.querySelector(".model-proposal-evidence-error");
      const saveButton = form.querySelector(".model-proposal-evidence-save");
      const evidenceId = form.dataset.evidenceId;

      const fields = {
        action: evidenceId ? "update_evidence" : "add_evidence",
        source: form.elements.source.value,
        locator: form.elements.locator.value,
        note: form.elements.note.value,
      };

      if (evidenceId) {
        fields.evidence_id = evidenceId;
      } else {
        fields.change_id = block.dataset.changeId;
      }

      errorEl.textContent = "";
      saveButton.disabled = true;

      try {
        const data = await evidencePost(fields);

        replaceEvidenceBlock(block, data.html);
      } catch (error) {
        console.error("Saving evidence failed:", error);
        errorEl.textContent = error.message;
        saveButton.disabled = false;
      }
    });

    changesContainer.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") {
        return;
      }

      const form = event.target.closest(".model-proposal-evidence-form");

      if (form) {
        closeEvidenceForm(form.closest(".model-proposal-evidence"));
      }
    });
  }

  // -------------------------------------------------------------
  // Change note (proposal-level, optional; editable proposals only).
  // -------------------------------------------------------------

  const noteSection = proposal.querySelector(
    ".model-proposal-change-note:not(.model-proposal-change-note-readonly)",
  );

  if (noteSection) {
    const noteInput = noteSection.querySelector(
      ".model-proposal-change-note-input",
    );
    const noteOpen = noteSection.querySelector(".model-proposal-change-note-open");
    const noteSave = noteSection.querySelector(".model-proposal-change-note-save");
    const noteCancel = noteSection.querySelector(
      ".model-proposal-change-note-cancel",
    );
    const noteStatus = noteSection.querySelector(
      ".model-proposal-change-note-status",
    );

    const setNoteStatus = (message, isError = false) => {
      noteStatus.textContent = message;
      noteStatus.classList.toggle("is-error", isError);
    };

    const syncNoteDirty = () => {
      noteSection.classList.toggle(
        "is-dirty",
        noteInput.value.trim() !== noteInput.dataset.saved.trim(),
      );
    };

    noteOpen.addEventListener("click", () => {
      delete noteSection.dataset.empty;
      noteInput.focus();
    });

    noteInput.addEventListener("input", () => {
      setNoteStatus("");
      syncNoteDirty();
    });

    noteCancel.addEventListener("click", () => {
      noteInput.value = noteInput.dataset.saved;
      setNoteStatus("");
      syncNoteDirty();

      if (!noteInput.dataset.saved.trim()) {
        noteSection.dataset.empty = "true";
      }
    });

    noteSave.addEventListener("click", async () => {
      noteSave.disabled = true;
      setNoteStatus("Saving…");

      try {
        const data = await evidencePost({
          action: "set_change_note",
          change_note: noteInput.value,
        });

        noteInput.value = data.change_note;
        noteInput.dataset.saved = data.change_note;
        syncNoteDirty();
        setNoteStatus("Saved");

        if (!data.change_note) {
          noteSection.dataset.empty = "true";
          setNoteStatus("");
        }
      } catch (error) {
        console.error("Saving change note failed:", error);
        setNoteStatus(error.message, true);
      } finally {
        noteSave.disabled = false;
      }
    });
  }

  // -------------------------------------------------------------
  // Rename (inline edit) -- available in any status.
  // -------------------------------------------------------------

  const titleDisplay = proposal.querySelector(".model-proposal-title-display");
  const titleInput = proposal.querySelector(".model-proposal-title-input");
  const renameBtn = proposal.querySelector(".model-proposal-rename-btn");

  if (renameBtn && titleInput && titleDisplay) {
    const openRename = () => {
      titleDisplay.style.display = "none";
      renameBtn.style.display = "none";
      titleInput.style.display = "";
      titleInput.focus();
      titleInput.select();
    };

    const commitRename = async () => {
      const newTitle = titleInput.value.trim();

      titleInput.style.display = "none";
      titleDisplay.style.display = "";
      renameBtn.style.display = "";

      try {
        const response = await postAction("rename", null, { title: newTitle });
        const data = await response.json();

        if (data.success) {
          titleDisplay.textContent = data.title || "Untitled proposal";
        }
      } catch (error) {
        console.error("Rename failed:", error);
        window.alert("The proposal could not be renamed. Please try again.");
      }
    };

    renameBtn.addEventListener("click", openRename);

    titleInput.addEventListener("blur", commitRename);

    titleInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        titleInput.blur();
      }
    });
  }

  // -------------------------------------------------------------
  // Submit ("Validate & Commit")
  // -------------------------------------------------------------

  const submitButton = proposal.querySelector(".model-proposal-submit");

  if (submitButton) {
    submitButton.addEventListener("click", () => {
      runAction("submit");
    });
  }

  // -------------------------------------------------------------
  // Abandon (two-step confirm, mirrors the per-change discard UI)
  // -------------------------------------------------------------

  const abandonButton = proposal.querySelector(".model-proposal-abandon");
  const abandonConfirm = proposal.querySelector(".model-proposal-abandon-confirm");

  if (abandonButton && abandonConfirm) {
    abandonButton.addEventListener("click", () => {
      abandonConfirm.classList.add("is-confirming");
    });

    const abandonNo = abandonConfirm.querySelector(
      ".model-proposal-abandon-confirm-no",
    );
    const abandonYes = abandonConfirm.querySelector(
      ".model-proposal-abandon-confirm-yes",
    );

    if (abandonNo) {
      abandonNo.addEventListener("click", () => {
        abandonConfirm.classList.remove("is-confirming");
      });
    }

    if (abandonYes) {
      abandonYes.addEventListener("click", () => {
        runAction("abandon");
      });
    }
  }

  // -------------------------------------------------------------
  // Acknowledge (COMPLETED only)
  // -------------------------------------------------------------

  const ackButton = proposal.querySelector(".model-proposal-acknowledge");

  if (ackButton) {
    ackButton.addEventListener("click", () => {
      runAction("acknowledge");
    });
  }
});
