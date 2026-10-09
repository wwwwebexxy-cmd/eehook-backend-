(function () {
  function toggleManualChoices() {
    var selected = document.querySelector('input[name="related_product_mode"]:checked');
    var manualRow = document.querySelector('.form-row.field-manual_related_products');
    if (!manualRow) return;
    manualRow.style.display = selected && selected.value === 'manual' ? '' : 'none';
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('input[name="related_product_mode"]').forEach(function (input) {
      input.addEventListener('change', toggleManualChoices);
    });
    toggleManualChoices();
  });
})();
