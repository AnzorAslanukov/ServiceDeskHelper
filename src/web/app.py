from flask import Flask, render_template, request, jsonify
import sys
import os

# Add the project root to Python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.processors.athena_operations import athena_ticket_advisor, find_similar_tickets

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('sd_helper.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    ticket_id = data.get('ticket_id')
    mode = data.get('mode')

    if not ticket_id or not mode:
        return jsonify({'error': 'Missing ticket_id or mode'}), 400

    try:
        if mode == 'ticket-routing':
            result = athena_ticket_advisor(ticket_id, log_debug=False)
            # Extract the specific keys
            response = {
                'support_group_assignment_group_name': result.get('support_group_assignment', {}).get('group_name'),
                'support_group_assignment_reason': result.get('support_group_assignment', {}).get('reason'),
                'priority_level_level': result.get('priority_level', {}).get('level'),
                'priority_level_classification': result.get('priority_level', {}).get('classification'),
                'priority_level_reason': result.get('priority_level', {}).get('reason'),
                'analysis_summary_business_impact': result.get('analysis_summary', {}).get('business_impact'),
                'analysis_summary_location_factor': result.get('analysis_summary', {}).get('location_factor'),
                'analysis_summary_similar_ticket_pattern': result.get('analysis_summary', {}).get('similar_ticket_pattern')
            }
            return jsonify(response)
        elif mode == 'find-similar':
            similar_tickets = find_similar_tickets(ticket_id, log_debug=False)
            # Normalize ticket_id key
            normalized_tickets = []
            for ticket in similar_tickets:
                norm_ticket = dict(ticket)
                if 'id' in norm_ticket and 'ticket_id' not in norm_ticket:
                    norm_ticket['ticket_id'] = norm_ticket.pop('id')
                normalized_tickets.append(norm_ticket)
            return jsonify({'similar_tickets': normalized_tickets})
        else:
            return jsonify({'error': 'Invalid mode'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
