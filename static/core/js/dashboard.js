const documentTypes = [
    { id: "title", label: "Title" },
    { id: "bill_of_sale", label: "Bill of Sale" },
    { id: "driver_license", label: "Driver License" },
    { id: "insurance_id", label: "Insurance ID Card" },
    { id: "mv82", label: "MV82" },
    { id: "dtf802", label: "DTF 802" },
    { id: "reassignments", label: "Reassignments" },
    { id: "mv50", label: "MV50" },
    { id: "other", label: "Other docs" },
];

let currentServiceId = null;
let currentVehicleId = null;

// File upload constraints
const MAX_FILE_SIZE_MB = 50;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

function isPDF(file) {
    return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
}
function isImage(file) {
    return file.type.startsWith('image/');
}
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
function getFileTypeIcon(file) {
    if (isPDF(file)) {
        return `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#e63946" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>`;
    }
    if (isImage(file)) {
        return `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>`;
    }
    return `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>`;
}

function openDocUploadModal(id, label, type = 'service') {
    if (type === 'service') {
        currentServiceId = id;
        currentVehicleId = null;
    } else {
        currentVehicleId = id;
        currentServiceId = null;
    }
    
    document.getElementById('modalReceiptDisplay').textContent = label;
    
    const docsContainer = document.getElementById('existing-docs-container');
    if (id) {
        fetchDocuments(id, type);
        docsContainer.style.display = 'block';
    } else {
        docsContainer.style.display = 'none';
    }
    
    const docGrid = document.querySelector('.doc-grid');
    docGrid.innerHTML = ''; // clear existing
    
    documentTypes.forEach(docType => {
        const dropzone = document.createElement('div');
        dropzone.className = 'dropzone';
        dropzone.id = `dropzone-${docType.id}`;
        
        dropzone.innerHTML = `
            <div class="dz-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="12" y1="18" x2="12" y2="12"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>
            </div>
            <div class="dz-text">${docType.label}</div>
            <div class="dz-hint" style="font-size:0.68rem;color:#94a3b8;margin-top:2px;">Image or PDF &middot; Up to ${MAX_FILE_SIZE_MB}MB</div>
            <div class="dz-status"></div>
            <input type="file" class="dz-input" data-doc-type="${docType.id}" accept="image/*,.pdf,application/pdf" style="display:none;">
        `;
        
        dropzone.style.position = 'relative';
        
        // Check if file is already attached (pre-upload)
        if (!currentServiceId && !currentVehicleId) {
            const hiddenInput = document.getElementById(`hidden-doc-${docType.id}`);
            if (hiddenInput && hiddenInput.files.length > 0) {
                dropzone.classList.add('success');
                dropzone.querySelector('.dz-status').textContent = 'Attached \u2713';
                
                const delBtn = document.createElement('span');
                delBtn.className = 'dz-remove';
                delBtn.innerHTML = '&times;';
                delBtn.title = 'Remove document';
                delBtn.style.cssText = 'position:absolute; top:2px; right:8px; cursor:pointer; color:#e63946; font-size:1.5rem; font-weight:bold; line-height:1; z-index:10;';
                delBtn.onclick = (e) => {
                    e.stopPropagation();
                    hiddenInput.value = ''; // clear file
                    dropzone.classList.remove('success');
                    dropzone.querySelector('.dz-status').textContent = '';
                    delBtn.remove();
                };
                dropzone.appendChild(delBtn);
            }
        }
        
        // Event listeners for drag and drop
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
        
        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });
        
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length) {
                handleFileUpload(files[0], docType.id, dropzone);
            }
        });
        
        dropzone.addEventListener('click', () => {
            dropzone.querySelector('.dz-input').click();
        });
        
        dropzone.querySelector('.dz-input').addEventListener('change', (e) => {
            if (e.target.files.length) {
                handleFileUpload(e.target.files[0], docType.id, dropzone);
            }
        });
        
        docGrid.appendChild(dropzone);
    });
    
    const drawerOverlay = document.getElementById('docUploadDrawer');
    drawerOverlay.style.display = 'block';
    
    // trigger reflow
    void drawerOverlay.offsetWidth;
    drawerOverlay.classList.add('open');
}

function closeDocUploadModal() {
    const drawerOverlay = document.getElementById('docUploadDrawer');
    drawerOverlay.classList.remove('open');
    setTimeout(() => {
        drawerOverlay.style.display = 'none';
        currentServiceId = null;
        currentVehicleId = null;
    }, 300); // Wait for transition
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function handleFileUpload(file, docType, dropzoneElement) {
    const statusDiv = dropzoneElement.querySelector('.dz-status');
    const iconDiv = dropzoneElement.querySelector('.dz-icon');

    // 1. Validate file type — only images or PDFs allowed
    if (!isImage(file) && !isPDF(file)) {
        dropzoneElement.classList.remove('success', 'uploading');
        dropzoneElement.classList.add('error');
        if (statusDiv) statusDiv.textContent = 'Only images or PDFs are allowed';
        dropzoneElement.classList.add('shake');
        setTimeout(() => dropzoneElement.classList.remove('shake'), 500);
        return;
    }

    // 2. Validate file size — max 50 MB
    if (file.size > MAX_FILE_SIZE_BYTES) {
        dropzoneElement.classList.remove('success', 'uploading');
        dropzoneElement.classList.add('error');
        if (statusDiv) statusDiv.textContent = `Too large: ${formatFileSize(file.size)} (max ${MAX_FILE_SIZE_MB}MB)`;
        dropzoneElement.classList.add('shake');
        setTimeout(() => dropzoneElement.classList.remove('shake'), 500);
        return;
    }

    // 3. Update icon to match file type
    if (iconDiv) iconDiv.innerHTML = getFileTypeIcon(file);

    // 4. Route: compress images, send PDFs as-is
    if (isImage(file) && typeof window.compressImage === 'function') {
        if (statusDiv) statusDiv.textContent = 'Compressing...';
        window.compressImage(file).then(compressedFile => {
            proceedWithUpload(compressedFile, docType, dropzoneElement);
        }).catch(err => {
            console.error('Compression failed:', err);
            proceedWithUpload(file, docType, dropzoneElement);
        });
    } else {
        if (statusDiv) statusDiv.textContent = `${formatFileSize(file.size)} — uploading...`;
        proceedWithUpload(file, docType, dropzoneElement);
    }
}

function proceedWithUpload(file, docType, dropzoneElement) {
    if (!currentServiceId && !currentVehicleId) {
        const dt = new DataTransfer();
        dt.items.add(file);
        
        let hiddenInput = document.getElementById(`hidden-doc-${docType}`);
        if (!hiddenInput) {
            hiddenInput = document.createElement('input');
            hiddenInput.type = 'file';
            hiddenInput.name = `doc_${docType}`;
            hiddenInput.id = `hidden-doc-${docType}`;
            hiddenInput.style.display = 'none';
            document.getElementById('hidden-file-inputs').appendChild(hiddenInput);
        }
        hiddenInput.files = dt.files;
        
        dropzoneElement.classList.remove('error', 'uploading');
        dropzoneElement.classList.add('success');
        dropzoneElement.querySelector('.dz-status').textContent = `Attached \u2713 (${formatFileSize(file.size)})`;
        
        if (!dropzoneElement.querySelector('.dz-remove')) {
            const delBtn = document.createElement('span');
            delBtn.className = 'dz-remove';
            delBtn.innerHTML = '&times;';
            delBtn.style.cssText = 'position:absolute; top:2px; right:8px; cursor:pointer; color:#e63946; font-size:1.5rem; font-weight:bold; line-height:1; z-index:10;';
            delBtn.onclick = (e) => {
                e.stopPropagation();
                hiddenInput.value = '';
                dropzoneElement.classList.remove('success');
                dropzoneElement.querySelector('.dz-status').textContent = '';
                delBtn.remove();
            };
            dropzoneElement.appendChild(delBtn);
        }
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', docType);
    
    let uploadUrl = currentServiceId
        ? `/dashboard/service/${currentServiceId}/upload/`
        : `/dashboard/vehicle/${currentVehicleId}/upload/`;
    
    const statusDiv = dropzoneElement.querySelector('.dz-status');
    dropzoneElement.classList.remove('success', 'error');
    dropzoneElement.classList.add('uploading');
    if (statusDiv) statusDiv.textContent = 'Uploading... 0%';

    // Use XHR so we can track upload progress and get proper HTTP status codes
    const xhr = new XMLHttpRequest();

    // --- Progress tracking ---
    xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && statusDiv) {
            const pct = Math.round((e.loaded / e.total) * 100);
            statusDiv.textContent = `Uploading... ${pct}%`;
        }
    });

    // --- Upload complete ---
    xhr.addEventListener('load', () => {
        dropzoneElement.classList.remove('uploading');
        if (xhr.status === 413) {
            // Nginx / server rejected upload as too large
            dropzoneElement.classList.add('error');
            if (statusDiv) statusDiv.textContent = 'File too large for server (413)';
            dropzoneElement.classList.add('shake');
            setTimeout(() => dropzoneElement.classList.remove('shake'), 500);
            return;
        }
        try {
            const data = JSON.parse(xhr.responseText);
            if (data.status === 'success') {
                dropzoneElement.classList.add('success');
                if (statusDiv) statusDiv.textContent = `Uploaded \u2713 (${formatFileSize(file.size)})`;
                // If there's a post-upload callback registered (e.g. vehicle detail page), call it
                if (typeof window._onUploadSuccess === 'function') {
                    window._onUploadSuccess(data, docType, dropzoneElement);
                }
            } else {
                dropzoneElement.classList.add('error');
                if (statusDiv) statusDiv.textContent = data.message || 'Upload failed';
                dropzoneElement.classList.add('shake');
                setTimeout(() => dropzoneElement.classList.remove('shake'), 500);
            }
        } catch (e) {
            dropzoneElement.classList.add('error');
            if (statusDiv) statusDiv.textContent = `Server error (${xhr.status})`;
            dropzoneElement.classList.add('shake');
            setTimeout(() => dropzoneElement.classList.remove('shake'), 500);
        }
    });

    // --- Network / timeout error ---
    const onError = () => {
        dropzoneElement.classList.remove('uploading');
        dropzoneElement.classList.add('error');
        if (statusDiv) statusDiv.textContent = 'Upload failed \u2014 check connection & server config';
        dropzoneElement.classList.add('shake');
        setTimeout(() => dropzoneElement.classList.remove('shake'), 500);
    };
    xhr.addEventListener('error', onError);
    xhr.addEventListener('timeout', () => {
        dropzoneElement.classList.remove('uploading');
        dropzoneElement.classList.add('error');
        if (statusDiv) statusDiv.textContent = 'Upload timed out \u2014 try a smaller file';
        dropzoneElement.classList.add('shake');
        setTimeout(() => dropzoneElement.classList.remove('shake'), 500);
    });

    xhr.open('POST', uploadUrl);
    xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));
    xhr.timeout = 120000; // 2-minute timeout
    xhr.send(formData);
}

function fetchDocuments(id, type = 'service') {
    let fetchUrl = (type === 'service') ? `/dashboard/service/${id}/docs/` : `/dashboard/vehicle/${id}/docs/`;

    fetch(fetchUrl)
    .then(response => response.json())
    .then(data => {
        const list = document.getElementById('existing-docs-list');
        list.innerHTML = '';
        if (data.documents && data.documents.length > 0) {
            data.documents.forEach(doc => {
                const url = doc.url || '';
                const isPdfDoc = url.toLowerCase().endsWith('.pdf');
                const iconColor = isPdfDoc ? '#e63946' : '#3b82f6';
                const iconSvg = isPdfDoc
                    ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>`
                    : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>`;
                const pdfBadge = isPdfDoc ? ` <span style="font-size:0.65rem;color:#e63946;font-weight:700;background:#fee2e2;padding:1px 5px;border-radius:4px;vertical-align:middle;">PDF</span>` : '';
                const viewLabel = isPdfDoc ? '📄 View PDF' : '🖼 View';

                const li = document.createElement('li');
                li.innerHTML = `
                    <div class="doc-info">
                        <div class="doc-icon" style="color:${iconColor};">${iconSvg}</div>
                        <span class="doc-name">${doc.type_label}${pdfBadge}</span>
                    </div>
                    <a href="${url}" target="_blank" class="btn btn-secondary btn-sm" style="min-height:auto; padding: 0.35rem 0.8rem; border-radius: 6px; font-size: 0.8rem;">${viewLabel}</a>
                `;
                list.appendChild(li);
            });
            document.getElementById('existing-docs-container').style.display = 'block';
        } else {
            document.getElementById('existing-docs-container').style.display = 'none';
        }
    })
    .catch(err => console.error(err));
}

function toggleAgentPermission(membershipId, field, isChecked) {
    const formData = new FormData();
    formData.append('membership_id', membershipId);
    formData.append('field', field);
    formData.append('value', isChecked ? 'true' : 'false');
    
    fetch('/dashboard/agent/permissions/', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        }
    })
    .then(response => response.json())
    .then(data => {
        if(data.status !== 'success') {
            alert('Failed to update permissions: ' + data.message);
        }
    })
    .catch(err => {
        alert('Network error updating permissions.');
    });
}

// Auto-open drawer on redirect if save_and_upload was triggered
window.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const uploadId = urlParams.get('upload');
    const receiptNum = urlParams.get('receipt') || uploadId;
    if (uploadId) {
        openDocUploadModal(uploadId, receiptNum);
        
        // Clean URL without reloading
        const newUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
        window.history.replaceState({path: newUrl}, '', newUrl);
    }
});

function openAddServiceModal() {
    const modal = document.getElementById('addServiceModal');
    modal.style.display = 'block';
    void modal.offsetWidth;
    modal.classList.add('open');
}

function closeAddServiceModal() {
    const modal = document.getElementById('addServiceModal');
    modal.classList.remove('open');
    setTimeout(() => {
        modal.style.display = 'none';
        document.getElementById('add-service-form').reset();
    }, 300);
}

function submitCustomService(e) {
    e.preventDefault();
    const orgId = document.getElementById('custom-service-org').value;
    const label = document.getElementById('custom-service-name').value;
    
    const formData = new FormData();
    formData.append('organization_id', orgId);
    formData.append('label', label);
    
    fetch('/dashboard/services/add-custom/', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        }
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            window.location.reload();
        } else {
            alert(data.message || 'Error creating custom service');
        }
    })
    .catch(err => alert('Network error creating service'));
}

function updateAgentRole(membershipId, role) {
    const formData = new FormData();
    formData.append('membership_id', membershipId);
    formData.append('role', role);
    
    fetch('/dashboard/agent/role/', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        }
    })
    .then(response => response.json())
    .then(data => {
        if(data.status !== 'success') {
            alert('Failed to update role: ' + data.message);
            window.location.reload(); // reload to reset dropdown
        } else {
            // Optional: visual indication of success
        }
    })
    .catch(err => {
        alert('Network error updating role.');
        window.location.reload();
    });
}

function toggleAgentActive(membershipId, isChecked) {
    fetch('/dashboard/agent/toggle-active/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({ membership_id: membershipId, enabled: isChecked })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status !== 'success') {
            alert(data.message || 'Failed to update agent status.');
            window.location.reload();
            return;
        }
        const badge = document.getElementById(`agent-status-${membershipId}`);
        const row = document.querySelector(`.agent-active-toggle[data-id="${membershipId}"]`)?.closest('.agent-row');
        if (badge) {
            badge.textContent = data.is_active ? 'Active' : 'Disabled';
            badge.classList.toggle('active', data.is_active);
            badge.classList.toggle('inactive', !data.is_active);
        }
        if (row) {
            row.classList.toggle('inactive-agent', !data.is_active);
        }
    })
    .catch(() => {
        alert('Network error updating agent status.');
        window.location.reload();
    });
}

function initializeDocUploadTriggers() {
    document.querySelectorAll('.doc-upload-trigger').forEach(btn => {
        btn.onclick = function() {
            openDocUploadModal(
                this.getAttribute('data-id'), 
                this.getAttribute('data-receipt'),
                this.getAttribute('data-type') || 'service'
            );
        };
    });
}
window.initializeDocUploadTriggers = initializeDocUploadTriggers;

document.addEventListener('DOMContentLoaded', () => {
    initializeDocUploadTriggers();

    // Payment Method & Fee Calculation Logic
    const paymentMethodSelect = document.getElementById('id_payment_method');
    const processingFeeInput = document.getElementById('id_processing_fee');
    const dmvFeeInput = document.getElementById('id_dmv_fee');
    const salesTaxInput = document.getElementById('id_sales_tax');
    const ccFeeInput = document.getElementById('id_credit_card_fee');

    function calculateCCFee() {
        if (!paymentMethodSelect || !ccFeeInput) return;
        
        const method = paymentMethodSelect.value;
        const processing = parseFloat(processingFeeInput?.value || 0);
        const dmv = parseFloat(dmvFeeInput?.value || 0);
        const tax = parseFloat(salesTaxInput?.value || 0);
        const subtotal = processing + dmv + tax;

        let fee = 0;
        // American Express: 5% credit card fee
        if (method === 'american_express') {
            fee = subtotal * 0.05;
        } else if (method === 'visa' || method === 'mastercard' || method === 'discover' || method === 'diners_club') {
            // Other credit cards: 3.5% credit card fee
            fee = subtotal * 0.035;
        }
        // Cash and Zelle: 0% (no credit card fee)
        
        ccFeeInput.value = fee.toFixed(2);
    }

    if (paymentMethodSelect) {
        paymentMethodSelect.addEventListener('change', calculateCCFee);
        processingFeeInput?.addEventListener('input', calculateCCFee);
        dmvFeeInput?.addEventListener('input', calculateCCFee);
        salesTaxInput?.addEventListener('input', calculateCCFee);
    }

    // Source dealer logic
    const sourceSelect = document.getElementById('id_source');
    
    // Agent management event listeners
    document.querySelectorAll('.agent-role-select').forEach(select => {
        select.addEventListener('change', function() {
            updateAgentRole(this.getAttribute('data-id'), this.value);
        });
    });

    document.querySelectorAll('.agent-permission-toggle').forEach(toggle => {
        toggle.addEventListener('change', function() {
            toggleAgentPermission(
                this.getAttribute('data-id'), 
                this.getAttribute('data-field'), 
                this.checked
            );
        });
    });

    document.querySelectorAll('.agent-active-toggle').forEach(toggle => {
        toggle.addEventListener('change', function() {
            toggleAgentActive(this.getAttribute('data-id'), this.checked);
        });
    });

    const dealerSelectWrap = document.getElementById('wrap_dealer_select');
    const dealerSelect = document.getElementById('id_dealer_select');
    const dealerBalanceWrap = document.getElementById('wrap_dealer_balance');
    const dealerNameWrap = document.getElementById('wrap_dealer_name');
    const dealerAddressWrap = document.getElementById('wrap_dealer_address');
    const dealerPhoneWrap = document.getElementById('wrap_dealer_phone_no');
    const dealerEmailWrap = document.getElementById('wrap_dealer_email');

    function toggleDealerFields() {
        if (!sourceSelect) return;
        const isDealer = sourceSelect.value === 'car dealer';
        
        if (dealerSelectWrap) dealerSelectWrap.style.display = isDealer ? 'block' : 'none';
        if (dealerBalanceWrap) dealerBalanceWrap.style.display = isDealer ? 'block' : 'none';
        
        if (isDealer) {
            const isNew = dealerSelect && dealerSelect.value === 'new';
            [dealerNameWrap, dealerAddressWrap, dealerPhoneWrap, dealerEmailWrap].forEach(el => {
                if (el) el.style.display = isNew ? 'block' : 'none';
            });
        } else {
            [dealerNameWrap, dealerAddressWrap, dealerPhoneWrap, dealerEmailWrap].forEach(el => {
                if (el) el.style.display = 'none';
            });
        }
    }

    if (sourceSelect) {
        sourceSelect.addEventListener('change', toggleDealerFields);
        if (dealerSelect) {
            dealerSelect.addEventListener('change', toggleDealerFields);
        }
        toggleDealerFields(); // Initial state
    }
});
