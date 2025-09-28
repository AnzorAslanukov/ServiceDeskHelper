document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.querySelector('.search-form');
    const searchInput = document.getElementById('search-input');
    const searchButton = document.getElementById('search-button');
    const warningMessage = document.getElementById('warning-message');
    const resultsDiv = document.getElementById('results');
    const loadingOverlay = document.getElementById('loading-overlay');
    const timerDiv = document.getElementById('timer');
    const modeRadios = document.querySelectorAll('input[name="mode"]');

    let currentMode = 'ticket-routing'; // Default mode

    function validateInput(value) {
        const trimmed = value.trim();
        const regex = /^(ir|sr)\d{7}$/i;
        return regex.test(trimmed);
    }

    function updateValidation() {
        const value = searchInput.value;
        const isValid = validateInput(value);
        const isEmpty = value.trim() === '';

        if (isValid) {
            warningMessage.style.display = 'none';
            searchButton.disabled = false;
        } else if (isEmpty) {
            warningMessage.style.display = 'none';
            searchButton.disabled = true;
        } else {
            warningMessage.style.display = 'block';
            searchButton.disabled = true;
        }
    }

    modeRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            currentMode = this.value;
            console.log('Mode changed to:', currentMode);
            // TODO: Implement mode-specific functionality
        });
    });

    searchInput.addEventListener('input', updateValidation);
    searchInput.addEventListener('change', updateValidation);

    // Initial validation
    updateValidation();

    searchForm.addEventListener('submit', function(event) {
        event.preventDefault();
        const query = searchInput.value.trim();
        if (validateInput(query)) {
            if (currentMode === 'ticket-routing') {
                // Show loading overlay
                loadingOverlay.style.display = 'flex';
                let seconds = 0;
                const timerInterval = setInterval(() => {
                    seconds++;
                    timerDiv.textContent = seconds + ' seconds';
                }, 1000);

                // Make API call
                fetch('/search', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        ticket_id: query,
                        mode: currentMode
                    })
                })
                .then(response => response.json())
                .then(data => {
                    clearInterval(timerInterval);
                    loadingOverlay.style.display = 'none';
                    if (data.error) {
                        resultsDiv.innerHTML = '<div class="error">Error: ' + data.error + '</div>';
                    } else {
                        // Create formatted HTML for ticket-routing
                        let html = '';

                        // Support Group Assignment
                        html += '<div class="result-section">';
                        html += '<h3>Support Group Assignment</h3>';
                        html += '<div class="result-item"><label>Group Name:</label> <span>' + (data.support_group_assignment_group_name || 'N/A') + '</span></div>';
                        html += '<div class="result-item"><label>Reason:</label> <span>' + (data.support_group_assignment_reason || 'N/A') + '</span></div>';
                        html += '</div>';

                        // Priority Level
                        html += '<div class="result-section">';
                        html += '<h3>Priority Level</h3>';
                        html += '<div class="result-item"><label>Level:</label> <span>' + (data.priority_level_level || 'N/A') + '</span></div>';
                        html += '<div class="result-item"><label>Classification:</label> <span>' + (data.priority_level_classification || 'N/A') + '</span></div>';
                        html += '<div class="result-item"><label>Reason:</label> <span>' + (data.priority_level_reason || 'N/A') + '</span></div>';
                        html += '</div>';

                        // Analysis Summary
                        html += '<div class="result-section">';
                        html += '<h3>Analysis Summary</h3>';
                        html += '<div class="result-item"><label>Business Impact:</label> <span>' + (data.analysis_summary_business_impact || 'N/A') + '</span></div>';
                        html += '<div class="result-item"><label>Location Factor:</label> <span>' + (data.analysis_summary_location_factor || 'N/A') + '</span></div>';
                        html += '<div class="result-item"><label>Similar Ticket Pattern:</label> <span>' + (data.analysis_summary_similar_ticket_pattern || 'N/A') + '</span></div>';
                        html += '</div>';

                        resultsDiv.innerHTML = html;
                    }
                    resultsDiv.style.display = 'block';
                })
                .catch(error => {
                    clearInterval(timerInterval);
                    loadingOverlay.style.display = 'none';
                    resultsDiv.innerHTML = '<div class="error">Error: ' + error.message + '</div>';
                    resultsDiv.style.display = 'block';
                });
            } else if (currentMode === 'find-similar') {
                // Show loading overlay for find-similar
                loadingOverlay.style.display = 'flex';
                let seconds = 0;
                const timerInterval = setInterval(() => {
                    seconds++;
                    timerDiv.textContent = seconds + ' seconds';
                }, 1000);

                // Make API call
                fetch('/search', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        ticket_id: query,
                        mode: currentMode
                    })
                })
                .then(response => response.json())
                .then(data => {
                    clearInterval(timerInterval);
                    loadingOverlay.style.display = 'none';
                    if (data.similar_tickets && Array.isArray(data.similar_tickets)) {
                        let html = '';
                        data.similar_tickets.forEach(ticket => {
                            html += '<div class="result-section orange">';
                            html += '<div class="collapsed"><span>' + (ticket.ticket_id || 'N/A') + '</span></div>';
                            html += '<div class="expanded" style="display: none;">';
                            html += '<div class="result-item"><label>Ticket ID:</label> <span>' + (ticket.ticket_id || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Title:</label> <span>' + (ticket.title || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Description:</label> <span>' + (ticket.description || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Escalated:</label> <span>' + (ticket.escalated || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Resolution Description:</label> <span>' + (ticket.resolution_description || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Message:</label> <span>' + (ticket.message || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Priority:</label> <span>' + (ticket.priority || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Location Name:</label> <span>' + (ticket.location_name || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Floor Name:</label> <span>' + (ticket.floor_name || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Affect Patient Care:</label> <span>' + (ticket.affect_patient_care || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Confirmed Resolution:</label> <span>' + (ticket.confirmed_resolution || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Tier Queue Name:</label> <span>' + (ticket.tier_queue_name || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Created Date:</label> <span>' + (ticket.created_date || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Last Modified:</label> <span>' + (ticket.last_modified || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Affected User Domain:</label> <span>' + (ticket.affected_user_domain || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Affected User Company:</label> <span>' + (ticket.affected_user_company || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Affected User Department:</label> <span>' + (ticket.affected_user_department || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Affected User Title:</label> <span>' + (ticket.affected_user_title || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Assigned To User Domain:</label> <span>' + (ticket.assigned_to_user_domain || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Assigned To User Company:</label> <span>' + (ticket.assigned_to_user_company || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Assigned To User Department:</label> <span>' + (ticket.assigned_to_user_department || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Assigned To User Title:</label> <span>' + (ticket.assigned_to_user_title || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Resolved By User Domain:</label> <span>' + (ticket.resolved_by_user_domain || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Resolved By User Company:</label> <span>' + (ticket.resolved_by_user_company || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Resolved By User Department:</label> <span>' + (ticket.resolved_by_user_department || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Resolved By User Title:</label> <span>' + (ticket.resolved_by_user_title || 'N/A') + '</span></div>';
                            if (ticket.analyst_comments) {
                                html += '<div class="result-item"><label>Analyst Comments:</label> <span>' + JSON.stringify(ticket.analyst_comments) + '</span></div>';
                            } else {
                                html += '<div class="result-item"><label>Analyst Comments:</label> <span>N/A</span></div>';
                            }
                            html += '</div>';
                            html += '</div>';
                        });
                        resultsDiv.innerHTML = html;
                        // Add click event listeners for toggling
                        const sections = resultsDiv.querySelectorAll('.result-section');
                        sections.forEach(section => {
                            section.addEventListener('click', () => {
                                section.classList.toggle('toggled');
                                const collapsed = section.querySelector('.collapsed');
                                const expanded = section.querySelector('.expanded');
                                if (section.classList.contains('toggled')) {
                                    collapsed.style.display = 'none';
                                    expanded.style.display = 'block';
                                } else {
                                    collapsed.style.display = 'block';
                                    expanded.style.display = 'none';
                                }
                            });
                        });
                    } else {
                        resultsDiv.innerHTML = '<div class="error">No similar tickets found.</div>';
                    }
                    resultsDiv.style.display = 'block';
                })
                .catch(error => {
                    clearInterval(timerInterval);
                    loadingOverlay.style.display = 'none';
                    resultsDiv.innerHTML = '<div class="error">Error: ' + error.message + '</div>';
                    resultsDiv.style.display = 'block';
                });
            } else if (currentMode === 'judge-ticket') {
                // Show loading overlay for judge-ticket
                loadingOverlay.style.display = 'flex';
                let seconds = 0;
                const timerInterval = setInterval(() => {
                    seconds++;
                    timerDiv.textContent = seconds + ' seconds';
                }, 1000);

                // Make API call
                fetch('/search', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        ticket_id: query,
                        mode: currentMode
                    })
                })
                .then(response => response.json())
                .then(data => {
                    clearInterval(timerInterval);
                    loadingOverlay.style.display = 'none';
                    if (data.error) {
                        resultsDiv.innerHTML = '<div class="error">Error: ' + data.error + '</div>';
                    } else {
                        // Create formatted HTML for judge-ticket
                        let html = '';

                        // Ticket Quality Assessment
                        if (data.ticket_quality_assessment) {
                            html += '<div class="result-section purple">';
                            html += '<h3>Ticket Quality Assessment</h3>';
                            html += '<div class="result-item"><label>Overall Rating:</label> <span>' + (data.ticket_quality_assessment.overall_rating || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Completeness Score:</label> <span>' + (data.ticket_quality_assessment.completeness_score || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Clarity Score:</label> <span>' + (data.ticket_quality_assessment.clarity_score || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Risk Level:</label> <span>' + (data.ticket_quality_assessment.risk_level || 'N/A') + '</span></div>';
                            html += '</div>';
                        }

                        // Missing Information
                        if (data.missing_information && Array.isArray(data.missing_information)) {
                            html += '<div class="result-section purple">';
                            html += '<h3>Missing Information</h3>';
                            data.missing_information.forEach(item => {
                                html += '<div class="result-item"><label>' + (item.category || 'N/A') + ':</label> <span>' + (item.missing_item || 'N/A') + ' (Importance: ' + (item.importance || 'N/A') + ') - ' + (item.reason_needed || 'N/A') + '</span></div>';
                            });
                            html += '</div>';
                        }

                        // Inconsistencies Found
                        if (data.inconsistencies_found && Array.isArray(data.inconsistencies_found)) {
                            html += '<div class="result-section purple">';
                            html += '<h3>Inconsistencies Found</h3>';
                            data.inconsistencies_found.forEach(item => {
                                html += '<div class="result-item"><label>' + (item.type || 'N/A') + ':</label> <span>' + (item.description || 'N/A') + ' - Impact: ' + (item.potential_impact || 'N/A') + '</span></div>';
                            });
                            html += '</div>';
                        }

                        // Recommendations
                        if (data.recommendations) {
                            html += '<div class="result-section purple">';
                            html += '<h3>Recommendations</h3>';
                            if (data.recommendations.immediate_actions && Array.isArray(data.recommendations.immediate_actions)) {
                                html += '<div class="result-item"><label>Immediate Actions:</label> <span>' + data.recommendations.immediate_actions.join(', ') + '</span></div>';
                            }
                            if (data.recommendations.ticket_improvements && Array.isArray(data.recommendations.ticket_improvements)) {
                                html += '<div class="result-item"><label>Ticket Improvements:</label> <span>' + data.recommendations.ticket_improvements.join(', ') + '</span></div>';
                            }
                            if (data.recommendations.follow_up_questions && Array.isArray(data.recommendations.follow_up_questions)) {
                                html += '<div class="result-item"><label>Follow-up Questions:</label> <span>' + data.recommendations.follow_up_questions.join(', ') + '</span></div>';
                            }
                            html += '</div>';
                        }

                        // Judgment Summary
                        if (data.judgment_summary) {
                            html += '<div class="result-section purple">';
                            html += '<h3>Judgment Summary</h3>';
                            html += '<div class="result-item"><label>Key Findings:</label> <span>' + (data.judgment_summary.key_findings || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Estimated Impact:</label> <span>' + (data.judgment_summary.estimated_impact || 'N/A') + '</span></div>';
                            html += '<div class="result-item"><label>Confidence Level:</label> <span>' + (data.judgment_summary.confidence_level || 'N/A') + '</span></div>';
                            html += '</div>';
                        }

                        resultsDiv.innerHTML = html;
                    }
                    resultsDiv.style.display = 'block';
                })
                .catch(error => {
                    clearInterval(timerInterval);
                    loadingOverlay.style.display = 'none';
                    resultsDiv.innerHTML = '<div class="error">Error: ' + error.message + '</div>';
                    resultsDiv.style.display = 'block';
                });
            }
        }
    });
});
