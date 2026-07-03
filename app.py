from flask import Flask, render_template, request, jsonify
import os
from dotenv import load_dotenv
from core.database import init_db, query_db, insert_db, delete_db, update_db
from core.algorithm import run_closest_pair, brute_force_closest_pair

# Load environment variables from the .env configuration file
load_dotenv()

# Manual fallback for loading .env/env if path contains unicode characters on Windows.
# This ensures environment variables (like API keys) are always loaded correctly.
if not os.getenv('GOOGLE_MAPS_API_KEY'):
    for env_name in ['.env', 'env']:
        env_path = os.path.join(os.path.dirname(__file__), env_name)
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            os.environ[k.strip()] = v.strip()
            except Exception as e:
                pass

# Initialize the Flask application
app = Flask(__name__)

# Initialize the SQLite database schema if database.db does not exist
init_db()

# --- WEB ROUTES ---

@app.route('/')
def index():
    """
    Renders the main map interface containing current emergency requests
    and nearby service units.
    """
    google_maps_api_key = os.getenv('GOOGLE_MAPS_API_KEY', 'YOUR_API_KEY_HERE').strip()
    return render_template('index.html', google_maps_api_key=google_maps_api_key)

@app.route('/places/<category>')
def places(category):
    """
    Renders the category-specific view (e.g., Hospitals, Police Stations, etc.)
    with maps integration and nearby resource details.
    """
    google_maps_api_key = os.getenv('GOOGLE_MAPS_API_KEY', 'YOUR_API_KEY_HERE').strip()
    
    # Metadata map to dynamically set labels, FontAwesome icons, and colors in UI
    category_info = {
        'hospital':     {'label': 'Hospitals',       'icon': 'fa-hospital',          'color': '#3b82f6'},
        'police':       {'label': 'Police Stations',  'icon': 'fa-shield-halved',     'color': '#818cf8'},
        'fire_station': {'label': 'Fire Stations',    'icon': 'fa-fire-extinguisher', 'color': '#f97316'},
        'supermarket':  {'label': 'Supermarkets',     'icon': 'fa-cart-shopping',     'color': '#10b981'},
        'pharmacy':     {'label': 'Pharmacies',       'icon': 'fa-pills',             'color': '#ec4899'},
        'gas_station':  {'label': 'Gas Stations',     'icon': 'fa-gas-pump',          'color': '#eab308'},
    }
    
    # Fallback for unknown categories
    info = category_info.get(category, {'label': category.replace('_', ' ').title(), 'icon': 'fa-map-pin', 'color': '#8b5cf6'})
    
    return render_template('places.html',
        google_maps_api_key=google_maps_api_key,
        category=category,
        category_label=info['label'],
        category_icon=info['icon'],
        category_color=info['color']
    )

@app.route('/admin')
def admin():
    """Renders the administrative dashboard for managing emergency services."""
    return render_template('admin.html')

@app.route('/dashboard')
def dashboard():
    """Renders analytical/statistical dashboard of emergency events and response speeds."""
    return render_template('dashboard.html')

@app.route('/education')
def education():
    """Renders the emergency preparedness and educational guide page."""
    return render_template('education.html')

# --- API ROUTES ---

@app.route('/api/services', methods=['GET'])
def get_services():
    """Fetches all registered services (hospitals, police, fire stations, etc.) from the DB."""
    services = query_db("SELECT * FROM services")
    return jsonify([dict(ix) for ix in services] if services else [])

@app.route('/api/services', methods=['POST'])
def add_service():
    """Adds a new emergency service unit to the database."""
    data = request.json
    service_id = insert_db(
        "INSERT INTO services (name, type, x, y, status, response_speed) VALUES (?, ?, ?, ?, ?, ?)",
        (data.get('name', 'Unknown'), data.get('type', 'hospital'), data.get('x', 0), data.get('y', 0), data.get('status', 'available'), data.get('response_speed', 10))
    )
    return jsonify({'id': service_id}), 201

@app.route('/api/services/<int:service_id>', methods=['DELETE'])
def remove_service(service_id):
    """Deletes a specific emergency service unit from the database by ID."""
    delete_db("DELETE FROM services WHERE id=?", (service_id,))
    return jsonify({'status': 'deleted'})

@app.route('/api/requests', methods=['GET'])
def get_requests():
    """Fetches all active emergency requests from the database."""
    reqs = query_db("SELECT * FROM requests")
    return jsonify([dict(ix) for ix in reqs] if reqs else [])

@app.route('/api/requests', methods=['POST'])
def add_request():
    """Registers a new active emergency/user request in the database."""
    data = request.json
    req_id = insert_db(
        "INSERT INTO requests (type, x, y) VALUES (?, ?, ?)",
        (data.get('type', 'medical'), data.get('x', 0), data.get('y', 0))
    )
    return jsonify({'id': req_id}), 201

@app.route('/api/algorithm/run', methods=['POST'])
def run_algorithm():
    """
    Executes both the Brute Force and Divide & Conquer closest-pair algorithms
    on a set of points (representing emergency sites and service units).
    """
    data = request.json
    points_data = data.get('points', [])

    if not points_data:
        return jsonify({'error': 'No points provided'}), 400

    # Convert JSON structures to tuples expected by the algorithm: (x, y, id, type, data_dict)
    formatted_points = []
    for p in points_data:
        ptype = p.get('type', 'service')
        formatted_points.append((p['x'], p['y'], p['id'], ptype, p))
    points_data = formatted_points

    if len(points_data) < 2:
        return jsonify({'error': 'Not enough points to find a pair'}), 400

    # Execute the Brute Force strategy
    bf_result = brute_force_closest_pair(points_data)

    # Execute the optimized Divide & Conquer strategy
    dc_result = run_closest_pair(points_data)

    def serialize_result(res):
        """Serializes the algorithm output to JSON-compatible data types."""
        cp = res.get('closest_pair')
        raw_dist = res.get('min_dist')
        # Map Inf / NaN values to None to prevent breaks in standard JSON parser
        dist = None if (raw_dist is None or raw_dist == float('inf') or raw_dist != raw_dist) else raw_dist
        return {
            'closest_pair': [cp[0][4], cp[1][4]] if cp else None,
            'min_dist': dist,
            'comparisons': res.get('comparisons', 0),
            'time_ms': res.get('time_ms', 0),
            'viz_steps': res.get('viz_steps', [])
        }

    return jsonify({
        'brute_force': serialize_result(bf_result),
        'divide_and_conquer': serialize_result(dc_result)
    })

@app.route('/api/algorithm/find_all', methods=['POST'])
def run_algorithm_all():
    """
    Finds the closest service unit of each key type (hospital, police, fire station)
    relative to a given emergency coordinate.
    """
    data = request.json
    points_data = data.get('points', [])
    
    formatted_points = []
    for p in points_data:
        formatted_points.append((p['x'], p['y'], p['id'], p['type'], p))
        
    emergencies = [p for p in formatted_points if p[3] == 'emergency']
    if not emergencies:
        return jsonify({'error': 'No emergency point found'}), 400
        
    emergency = emergencies[0] # assume the primary emergency anchor
    
    results = {}
    total_time = 0
    
    for stype in ['hospital', 'police', 'fire']:
        # Filter point set to include the current emergency and services of this specific sub-category
        subset = [emergency] + [p for p in formatted_points if p[3] == 'service' and p[4].get('subtype') == stype]
        if len(subset) > 1:
            res = run_closest_pair(subset)
            total_time += res['time_ms']
            results[stype] = res
        else:
            results[stype] = None
            
    return jsonify({
        'results': results,
        'total_time_ms': total_time
    })

if __name__ == '__main__':
    # Run the application locally on port 5000
    app.run(debug=True, port=5000)
