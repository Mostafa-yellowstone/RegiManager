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

    function syncReviewLinkVisibility(showButton, immediate) {
        var $row = $('.field-review_link');
        if (showButton) {
            if (immediate) $row.show();
            else $row.slideDown();
        } else {
            if (immediate) $row.hide();
            else $row.slideUp();
        }
    }

    $(document).ready(function() {
        var $automationCheckbox = $('#id_is_automation_enabled');
        var $reviewCheckbox = $('#id_show_review_button');

        // Automation toggle
        if ($automationCheckbox.length > 0) {
            syncAutomationVisibility($automationCheckbox.is(':checked'));
            $automationCheckbox.on('change', function() {
                syncAutomationVisibility($(this).is(':checked'));
            });
        }

        // Review link toggle
        if ($reviewCheckbox.length > 0) {
            syncReviewLinkVisibility($reviewCheckbox.is(':checked'), true);
            $reviewCheckbox.on('change', function() {
                syncReviewLinkVisibility($(this).is(':checked'), false);
            });
        }
    });

})(django.jQuery);
