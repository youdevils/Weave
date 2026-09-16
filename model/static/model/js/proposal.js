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
