(function () {
  "use strict";

  var input = document.getElementById("assistedReconcileEvidence");
  var list = document.getElementById("assistedReconcileFileList");

  if (!input || !list) {
    return;
  }

  function humanizeBytes(bytes) {
    if (bytes < 1024) {
      return bytes + " B";
    }
    if (bytes < 1024 * 1024) {
      return (bytes / 1024).toFixed(1) + " KB";
    }
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  input.addEventListener("change", function () {
    list.innerHTML = "";

    if (input.files.length === 0) {
      var empty = document.createElement("li");
      empty.className = "assisted-file-list-empty";
      empty.textContent = "No files selected";
      list.appendChild(empty);
      return;
    }

    Array.prototype.forEach.call(input.files, function (file) {
      var item = document.createElement("li");
      item.className = "assisted-file-list-item";

      var name = document.createElement("span");
      name.textContent = file.name;

      var size = document.createElement("span");
      size.className = "assisted-file-list-item-size";
      size.textContent = humanizeBytes(file.size);

      item.appendChild(name);
      item.appendChild(size);
      list.appendChild(item);
    });
  });
})();
