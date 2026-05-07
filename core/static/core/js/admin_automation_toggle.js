(function($) {
    'use strict';

    function getAutomationRows() {
        // Targets the can_trigger_automation field in the inline table headers and cells
        return {
            headers: $('th.column-can_trigger_automation'),
            cells: $('td.field-can_trigger_automation'),
        };
    }

    function syncAutomationVisibility(isEnabled) {
        var rows = getAutomationRows();
        if (isEnabled) {
            rows.headers.show();
            rows.cells.show();
        } else {
            rows.headers.hide();
            rows.cells.hide();
        }
    }

    $(document).ready(function() {
        var $automationCheckbox = $('#id_is_automation_enabled');

        if ($automationCheckbox.length === 0) {
            return; // Not on the Organization change page
        }

        // Set initial state on page load
        syncAutomationVisibility($automationCheckbox.is(':checked'));

        // React to any change
        $automationCheckbox.on('change', function() {
            syncAutomationVisibility($(this).is(':checked'));
        });
    });

})(django.jQuery);
