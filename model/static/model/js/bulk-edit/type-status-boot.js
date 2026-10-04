/**
 * Type index (ObjectType, RelationshipType) — bulk Activate/Deactivate.
 * Lifecycle-only: this never grows into generic bulk editing of types
 * (attributes, relationships, cardinalities, identities stay
 * single-item-only). Which POST action and id field to use comes from
 * the form's data-bulk-status-action/data-bulk-id-field attributes, so
 * this one script serves every type index uniformly.
 *
 * Unlike the data Object bulk editor (a dedicated page), this reuses the
 * index page's own AJAX-action convention (model_editing.js's
 * postForm/getCsrfToken pattern) rather than a full-page navigation, since
 * a lifecycle toggle has no multi-field review step to show.
 */

function getCsrfToken() {
  const input = document.querySelector('[name="csrfmiddlewaretoken"]');
  if (input && input.value) return input.value;

  const cookies = document.cookie.split(";");
  for (let cookie of cookies) {
    cookie = cookie.trim();
    if (cookie.startsWith("csrftoken=")) {
      return decodeURIComponent(cookie.substring("csrftoken=".length));
    }
  }
  return null;
}

export function initTypeStatusBulkActions(root) {
  if (!root) return;

  const buttons = Array.from(root.querySelectorAll("[data-bulk-type-status]"));
  if (buttons.length === 0) return;

  const statusAction = root.dataset.bulkStatusAction;
  const idField = root.dataset.bulkIdField;
  if (!statusAction || !idField) return;

  function selectedIds() {
    return Array.from(root.querySelectorAll("[data-bulk-select]:checked")).map(
      (checkbox) => checkbox.value,
    );
  }

  buttons.forEach((button) => {
    button.addEventListener("click", async () => {
      const ids = selectedIds();
      if (ids.length === 0) return;

      const body = new URLSearchParams();
      body.set("action", statusAction);
      body.set("is_active", button.dataset.bulkTypeStatus);
      ids.forEach((id) => body.append(idField, id));

      const response = await fetch(window.location.pathname, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCsrfToken(),
          "X-Requested-With": "XMLHttpRequest",
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body,
      });

      const payload = await response.json().catch(() => ({ success: false }));

      if (payload.success) {
        window.location.reload();
        return;
      }

      window.alert(payload.error || "Could not update the selected items.");
    });
  });
}

if (typeof document !== "undefined") {
  document
    .querySelectorAll("[data-bulk-select-form]")
    .forEach((root) => initTypeStatusBulkActions(root));
}
