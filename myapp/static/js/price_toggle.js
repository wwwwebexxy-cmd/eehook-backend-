document.addEventListener("DOMContentLoaded", function() {
    function toggleFields(row) {
        var priceTypeRadios = row.querySelectorAll('input[type="radio"][name$="-price_type"]');
        var priceType = null;
        for (var i = 0; i < priceTypeRadios.length; i++) {
            if (priceTypeRadios[i].checked) {
                priceType = priceTypeRadios[i].value;
                break;
            }
        }

        if (!priceType) return;

        var priceField = row.querySelector('.field-price');
        var sizesInline = row.querySelector('.inline-group[id$="-sizes-group"]');

        if (priceType === 'single') {
            if (priceField) priceField.style.display = 'block';
            if (sizesInline) sizesInline.style.display = 'none';
        } else if (priceType === 'multiple') {
            if (priceField) priceField.style.display = 'none';
            if (sizesInline) sizesInline.style.display = 'block';
        }
    }

    function initRow(row) {
        if (!row.classList.contains('has_original') && !row.classList.contains('dynamic-form')) return;
        var priceTypeRadios = row.querySelectorAll('input[type="radio"][name$="-price_type"]');
        for (var i = 0; i < priceTypeRadios.length; i++) {
            priceTypeRadios[i].addEventListener('change', function() {
                toggleFields(row);
            });
        }
        toggleFields(row);
    }

    // Initialize existing rows
    var rows = document.querySelectorAll('.dynamic-variants, .inline-related');
    rows.forEach(initRow);

    // Watch for newly added nested inlines (mutation observer because django-nested-admin adds them dynamically)
    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === 1 && (node.classList.contains('inline-related') || node.classList.contains('dynamic-variants'))) {
                    initRow(node);
                }
            });
        });
    });

    observer.observe(document.body, { childList: true, subtree: true });
});
