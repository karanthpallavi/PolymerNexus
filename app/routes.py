from flask import Blueprint, render_template, request, Response, current_app,jsonify, send_file
import os
import time
from werkzeug.utils import secure_filename
from .utils import generate_output_filename, readIndivSheetsTransformToCSV, preprocessSSBRRequestsFile, \
    readOntologyCSVAndBuildDataTriples, process_directory, upload_to_graphdb, run_sparql_query
from os import listdir
from os.path import isfile, join
import csv
import io
#from bs4 import BeautifulSoup
import pandas as pd
import requests

bp = Blueprint('main', __name__, template_folder='templates')

GRAPHDB_ENDPOINT = "http://localhost:7200/repositories/ArlanxeoPolymers"

PROPERTY_LABEL_MAP = {
    # keys should match the <option value="..."> in your HTML
    "MSR": "MSR",
    "Mooney Stress Relaxation": "Mooney Stress Relaxation",
    "Mooney": "Mooney Stress Relaxation",  # keep if older forms still send this
    "Hardness": "Hardness_mean_value",
    "Styrene": "Styrene_Cont",
    "Vinyl": "Vinyl_Cont",
    "GlassTransition": "Glass transition temperature",
    "Cis": "Cis_Cont",
    "Trans": "Trans_Cont",
    # add more mappings here as needed
}
# Check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

# Streaming generator for progress
def generate_progress_messages():
    steps = [
        "Starting file upload...",
        "Validating file...",
        "Saving file...",
        "Transforming raw data file to specific template csv files...",
        "Generating graph files in ttl format from template csv files...",
        "Graph files generated, Please check the output folder for template csv files generated and output/output_valid_graphs folder for graph files!...",
        "Uploading graph files to GraphDB Repository",
        "Use endpoint - http://127.0.0.1:5000/query to query the data in GraphDB"
    ]
    for step in steps:
        yield f"data:{step}\n\n"
        time.sleep(1)  # Simulate processing time

@bp.route("/generate_csv", methods=["POST"])
def generate_csv():
    try:
        # Get table data from request
        data = request.json.get("data", [])
        if not data:
            return jsonify({"error": "No data received"}), 400

        # Convert to DataFrame and save as CSV in memory
        df = pd.DataFrame(data[1:], columns=data[0])  # First row is headers
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)

        # Send the CSV file as a response
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name="query_results.csv"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/generate_excel", methods=["POST"])
def generate_excel():
    try:
        data = request.json.get("data", [])
        if not data or len(data) < 2:  # Ensure there are headers and at least one row
            return jsonify({"error": "No valid data received"}), 400

        df = pd.DataFrame(data[1:], columns=data[0])  # First row is headers

        # Create an in-memory BytesIO buffer for the Excel file
        output = io.BytesIO()

        # Use `ExcelWriter` to properly write the DataFrame into an Excel file
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="QueryResults")
            writer.book.close()  # Ensure all writes are properly closed

        # Move back to the beginning of the buffer so Flask can read it
        output.seek(0)

        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="query_results.xlsx"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Home route
@bp.route('/')
def home():
    return render_template('upload.html')

# Upload route
@bp.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        current_app.logger.warning("No file part in the request.")  # Log at WARNING level
        return "No file part", 400

    file = request.files['file']
    if file.filename == '':
        current_app.logger.warning("No file selected for uploading.")  # Log at WARNING level
        return "No selected file", 400

    if not allowed_file(file.filename):
        return "Invalid file type. Please upload an excel file", 400

    try:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        current_app.logger.info(f"File uploaded: {file.filename}")  # Log at INFO level
        templateFilePath = os.path.join(current_app.config['UPLOAD_FOLDER'],'templateFile.csv')

        # Read the Excel file into a Pandas DataFrame
        #df = pd.read_excel(filepath)

        # Call generate schema functions here
        preprocessSSBRRequestsFile(file_path,templateFilePath)

        owlFilePath = os.path.join(current_app.config['UPLOAD_FOLDER'],'digitrubber-full.ttl')

        #Call to generate ttl files for generated/transformed csv files
        onlyfiles = [f for f in listdir(current_app.config['OUTPUT_FOLDER']) if isfile(join(current_app.config['OUTPUT_FOLDER'], f))]
        current_app.logger.info(f"File to generate Graph from:",onlyfiles)

        for eachFile in onlyfiles:
            eachFileFullPath = (current_app.config['OUTPUT_FOLDER'])+"//"+eachFile
            fileNameWithoutExt = eachFile[:-4]
            #print("File name without ext ",fileNameWithoutExt)
            readOntologyCSVAndBuildDataTriples(owlFilePath,eachFileFullPath,fileNameWithoutExt)
        input_directory = current_app.config['OUTPUT_GRAPH_FOLDER']
        output_directory = "output_valid_graphs/"
        process_directory(input_directory, output_directory)

        # Upload TTL files to GraphDB with secure credentials
        username = current_app.config.get('GRAPHDB_USERNAME')
        password = current_app.config.get('GRAPHDB_PASSWORD')
        for ttl_file in os.listdir(output_directory):
            ttl_path = os.path.join(output_directory, ttl_file)
            graphdb_repo_url = f"http://localhost:7200/repositories/{current_app.config['GRAPHDB_REPO']}"
            upload_to_graphdb(graphdb_repo_url, ttl_path, username, password)
            #upload_to_graphdb(current_app.config['GRAPHDB_REPO'], ttl_path, username, password)

        return Response(generate_progress_messages(), content_type='text/event-stream')

    except Exception as e:
        return f"An error occurred: {e}"

def make_filter(label_var, value_var, comparison, threshold, quality_label):
    op = ">" if comparison == "greater" else "<"
    return f'''
        FILTER(CONTAINS(LCASE(STR(?{label_var})), LCASE("{quality_label}")))
        FILTER(?{value_var} {op} {threshold})
    '''

def build_max_value_query(property_label):
    return f"""
PREFIX iao: <http://purl.obolibrary.org/obo/iao.owl/>
PREFIX obi: <http://purl.obolibrary.org/obo/obi.owl/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?object ?quality ?maximumvalue
WHERE {{
  ?smd rdf:type iao:IAO_0000032 ;
       iao:IAO_0000221 ?quality_uri ;
       iao:IAO_0000136 ?object_uri ;
       obi:OBI_0001938 ?valuespec .
  ?valuespec obi:OBI_0001937 ?maximumvalue .
  ?object_uri rdfs:label ?object .
  ?quality_uri rdfs:label ?quality .

  VALUES ?quality {{ "{property_label}" }}

  {{
    SELECT (MAX(xsd:double(?v)) AS ?maxVal)
    WHERE {{
      ?smd2 rdf:type iao:IAO_0000032 ;
            iao:IAO_0000221 ?q2 ;
            obi:OBI_0001938 ?vs2 .
      ?vs2 obi:OBI_0001937 ?v .
      ?q2 rdfs:label ?qlabel .

      VALUES ?qlabel {{ "{property_label}" }}
    }}
  }}

  FILTER(xsd:double(?maximumvalue) = ?maxVal)
}}
"""

def build_min_value_query(property_label):
    return f"""
PREFIX iao: <http://purl.obolibrary.org/obo/iao.owl/>
PREFIX obi: <http://purl.obolibrary.org/obo/obi.owl/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?object ?quality ?minimumvalue
WHERE {{
  ?smd rdf:type iao:IAO_0000032 ;
       iao:IAO_0000221 ?quality_uri ;
       iao:IAO_0000136 ?object_uri ;
       obi:OBI_0001938 ?valuespec .
  ?valuespec obi:OBI_0001937 ?minimumvalue .
  ?object_uri rdfs:label ?object .
  ?quality_uri rdfs:label ?quality .

  VALUES ?quality {{ "{property_label}" }}

  {{
    SELECT (MIN(xsd:double(?v)) AS ?minVal)
    WHERE {{
      ?smd2 rdf:type iao:IAO_0000032 ;
            iao:IAO_0000221 ?q2 ;
            obi:OBI_0001938 ?vs2 .
      ?vs2 obi:OBI_0001937 ?v .
      ?q2 rdfs:label ?qlabel .

      VALUES ?qlabel {{ "{property_label}" }}
    }}
  }}

  FILTER(xsd:double(?minimumvalue) = ?minVal)
}}
"""

def get_label_for_property(key):
    return PROPERTY_LABEL_MAP.get(key, key)

@bp.route('/query', methods=['GET', 'POST'])
def query_graphdb():
    if request.method == 'GET':
        return render_template('query_form.html')

    template = request.form.get("template")
    print("Template selected:", template)

    if template == "max_value_query":
        prop_key = request.form.get("property")
        if not prop_key:
            return "Missing property", 400

        prop_label = get_label_for_property(prop_key)
        sparql_query = build_max_value_query(prop_label)

    elif template == "min_value_query":
        prop_key = request.form.get("property")
        if not prop_key:
            return "Missing property", 400

        prop_label = get_label_for_property(prop_key)
        sparql_query = build_min_value_query(prop_label)

    elif template == "multi_property_comparison":
        prop1_label = get_label_for_property(request.form.get("property1"))
        prop2_label = get_label_for_property(request.form.get("property2"))

        comp1 = request.form.get("comparison1")
        comp2 = request.form.get("comparison2")

        val1 = float(request.form.get("value1"))
        val2 = float(request.form.get("value2"))

        op1 = ">" if comp1 == "greater" else "<"
        op2 = ">" if comp2 == "greater" else "<"

        sparql_query = f"""
PREFIX iao: <http://purl.obolibrary.org/obo/iao.owl/>
PREFIX obi: <http://purl.obolibrary.org/obo/obi.owl/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?object ?prop1_quality ?val1 ?prop2_quality ?val2 
WHERE {{
  ?object_uri rdfs:label ?object .

  ?smd1 rdf:type iao:IAO_0000032 ;
        iao:IAO_0000136 ?object_uri ;
        iao:IAO_0000221 ?p1 ;
        obi:OBI_0001938 ?vs1 .
  ?p1 rdfs:label ?prop1_quality .
  ?vs1 obi:OBI_0001937 ?val1 .

  ?smd2 rdf:type iao:IAO_0000032 ;
        iao:IAO_0000136 ?object_uri ;
        iao:IAO_0000221 ?p2 ;
        obi:OBI_0001938 ?vs2 .
  ?p2 rdfs:label ?prop2_quality .
  ?vs2 obi:OBI_0001937 ?val2 .

  VALUES ?prop1_quality {{ "{prop1_label}" }}
  VALUES ?prop2_quality {{ "{prop2_label}" }}

  FILTER(xsd:double(?val1) {op1} {val1})
  FILTER(xsd:double(?val2) {op2} {val2})
}}
"""

    elif template == "filter_by_single_quality":
        prop_label = get_label_for_property(request.form.get("property"))
        operator = request.form.get("operator")

        # Convert values manually
        try:
            val1 = float(request.form.get("value1"))
        except (TypeError, ValueError):
            val1 = None
        val2_raw = request.form.get("value2")
        try:
            val2 = float(val2_raw) if val2_raw else None
        except ValueError:
            val2 = None

        if not prop_label or val1 is None or (operator == "range" and val2 is None):
            return "Missing required values for single quality filter.", 400

        # Build filter string
        filters = ""
        if operator == "above":
            filters = f"FILTER(?numericvalue > {val1})"
        elif operator == "below":
            filters = f"FILTER(?numericvalue < {val1})"
        elif operator == "equals":
            filters = f"FILTER(?numericvalue = {val1})"
        elif operator == "range":
            filters = f"FILTER(?numericvalue >= {val1} && ?numericvalue <= {val2})"
        else:
            return "Invalid operator", 400

        # Construct SPARQL
        sparql_query = f"""
    PREFIX iao: <http://purl.obolibrary.org/obo/iao.owl/>
    PREFIX obi: <http://purl.obolibrary.org/obo/obi.owl/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?object ?quality ?numericvalue WHERE {{
    ?smd rdf:type iao:IAO_0000032.
    ?smd iao:IAO_0000221 ?quality_uri.
    ?smd iao:IAO_0000136 ?object_uri.
    ?smd obi:OBI_0001938 ?valuespec.
    ?valuespec obi:OBI_0001937 ?numericvalue.
    ?object_uri rdfs:label ?object.
    ?quality_uri rdfs:label ?quality.
    VALUES ?quality {{ "{prop_label}" }}
    {filters}
    }}
    """
    else:
        return "Invalid template", 400

    print("\n✅ Generated SPARQL:\n", sparql_query)

    response = requests.post(
        GRAPHDB_ENDPOINT,
        data=sparql_query.encode("utf-8"),
        headers={
            "Content-Type": "application/sparql-query",
            "Accept": "application/sparql-results+json"
        }
    )

    if response.status_code != 200:
        return f"GraphDB error: {response.text}", 500

    results = response.json().get("results", {}).get("bindings", [])
    return render_template(
        "query_results.html",
        results=results,
        template_name=template
    )
    #return jsonify(results)


@bp.route('/query_working', methods=['GET', 'POST'])
def query_graphdb_working():
    if request.method == 'GET':
        return render_template('query_form.html')

    # --- stable mapping from option value (form) -> actual rdfs:label in RDF ---
    PROPERTY_LABEL_MAP = {
        # keys should match the <option value="..."> in your HTML
        "MSR": "MSR",
        "Mooney Stress Relaxation": "Mooney Stress Relaxation",
        "Mooney": "Mooney Stress Relaxation",  # keep if older forms still send this
        "Hardness": "Hardness mean value",
        "Styrene": "Styrene_Cont",
        "Vinyl": "Vinyl_Cont",
        "GlassTransition": "Glass transition temperature",
        "Cis": "Cis_Cont",
        "Trans": "Trans_Cont",
        # add more mappings here as needed
    }

    template = request.form.get("template")

    prefixes = """
PREFIX iao: <http://purl.obolibrary.org/obo/iao.owl/>
PREFIX obi: <http://purl.obolibrary.org/obo/obi.owl/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX schema: <http://schema.org/>
PREFIX pmd: <https://w3id.org/pmd/co/>
PREFIX obo: <http://purl.obolibrary.org/obo/>
PREFIX bfo: <http://purl.obolibrary.org/obo/bfo.owl/>
PREFIX isk: <https://tib.eu/ontologies/isk/>
PREFIX time: <http://www.w3.org/2006/time/>
PREFIX stato: <http://purl.obolibrary.org/stato.owl/>
"""

    # helper to get RDF label (fallback to the raw prop if not in map)
    def get_label_for_property(prop_key):
        if prop_key is None:
            return None
        return PROPERTY_LABEL_MAP.get(prop_key, prop_key)

    # build a safe regex filter for a given label var and label text
    def regex_filter(label_var, label_text):
        # escape double-quotes inside label_text just in case
        safe_label = str(label_text).replace('"', '\\"')
        return f'FILTER(REGEX(STR(?{label_var}), "{safe_label}", "i"))'

    def values_filter(var_name: str, label: str) -> str:
        return f'VALUES ?{var_name} {{ "{label}" }}'

    if template == "filter_by_single_quality":
        prop_key = request.form.get("property")      # this should be an internal key like "MSR"
        operator = request.form.get("operator")
        val1 = request.form.get("value1", type=float)
        val2 = request.form.get("value2", type=float)

        if not prop_key or val1 is None or (operator == "range" and val2 is None):
            return "Missing required values for single quality filter.", 400

        # map key to actual RDF label to search for
        prop_label = get_label_for_property(prop_key)
        # build filter
        filters = regex_filter("quality", prop_label) + "\n"
        if operator == "above":
            filters += f"FILTER(?numericvalue > {val1})"
        elif operator == "below":
            filters += f"FILTER(?numericvalue < {val1})"
        elif operator == "equals":
            filters += f"FILTER(?numericvalue = {val1})"
        elif operator == "range":
            filters += f"FILTER(?numericvalue >= {val1} && ?numericvalue <= {val2})"
        else:
            return "Invalid operator", 400

        where_clause = f"""
SELECT ?object ?quality ?numericvalue WHERE {{
  ?smd rdf:type iao:IAO_0000032.
  ?smd iao:IAO_0000221 ?quality_uri.
  ?smd iao:IAO_0000136 ?object_uri.
  ?smd obi:OBI_0001938 ?valuespec.
  ?valuespec obi:OBI_0001937 ?numericvalue.
  ?object_uri rdfs:label ?object.
  ?quality_uri rdfs:label ?quality.
  {filters}
}}
"""

    elif template == "multi_property_comparison":
        prop1_key = request.form.get("property1")
        comp1 = request.form.get("comparison1")
        val1 = request.form.get("value1", type=float)
        val1b_raw = request.form.get("value1b")     # for range
        val1b = float(val1b_raw) if val1b_raw else None

        prop2_key = request.form.get("property2")
        comp2 = request.form.get("comparison2")
        val2 = request.form.get("value2", type=float)
        val2b_raw = request.form.get("value2b")     # for range
        val2b = float(val2b_raw) if val2b_raw else None

        if not all([prop1_key, comp1, val1 is not None, prop2_key, comp2, val2 is not None]):
            return "All values required for multi-property comparison.", 400

        prop1_label = get_label_for_property(prop1_key)
        prop2_label = get_label_for_property(prop2_key)

        # Keep your existing VALUES filters
        filters1 = values_filter("prop1_quality", prop1_label)
        filters2 = values_filter("prop2_quality", prop2_label)

        # ---- NUMERIC FILTER BUILDER (minimal change) ----
        def build_numeric_filter(varname, comp, vlow, vhigh):
            if comp == "greater":
                return f"FILTER(?{varname} > {vlow})"
            elif comp == "less":
                return f"FILTER(?{varname} < {vlow})"
            elif comp == "equals":
                return f"FILTER(?{varname} = {vlow})"
            elif comp == "range":
                return f"FILTER(?{varname} >= {vlow} && ?{varname} <= {vhigh})"
            else:
                return ""

        # Apply to both properties
        filters1 += "\n" + build_numeric_filter("val1", comp1, val1, val1b)
        filters2 += "\n" + build_numeric_filter("val2", comp2, val2, val2b)

        where_clause = f'''
SELECT ?object ?prop1_quality ?val1 ?prop2_quality ?val2 
WHERE {{
  ?object_uri rdfs:label ?object .

  # First measurement
  ?smd1 rdf:type iao:IAO_0000032 ;
        iao:IAO_0000136 ?object_uri ;
        iao:IAO_0000221 ?prop1_uri ;
        obi:OBI_0001938 ?valspec1 .
  ?prop1_uri rdfs:label ?prop1_quality .
  ?valspec1 obi:OBI_0001937 ?val1 .

  # Second measurement
  ?smd2 rdf:type iao:IAO_0000032 ;
        iao:IAO_0000136 ?object_uri ;
        iao:IAO_0000221 ?prop2_uri ;
        obi:OBI_0001938 ?valspec2 .
  ?prop2_uri rdfs:label ?prop2_quality .
  ?valspec2 obi:OBI_0001937 ?val2 .

  # Filters
  {filters1}
  {filters2}
}}
'''

    elif template == "min_value_query":
        property_label = request.form.get("property")
        query_text = build_min_value_query(property_label)

        response = request.post(
            GRAPHDB_ENDPOINT,
            data=query_text.encode("utf-8"),
            headers={"Content-Type": "application/sparql-query",
                     "Accept": "application/sparql-results+json"}
        )

        results = response.json().get("results", {}).get("bindings", [])
        return jsonify(results)
    else:
        return "Invalid template selected.", 400

    full_query = prefixes + where_clause

    try:
        # debug: print constructed SPARQL
        print("DEBUG - Full SPARQL Query:\n", full_query)

        repo_url = f"http://localhost:7200/repositories/{current_app.config['GRAPHDB_REPO']}"
        username = current_app.config.get('GRAPHDB_USERNAME')
        password = current_app.config.get('GRAPHDB_PASSWORD')

        results = run_sparql_query(repo_url, full_query, username, password)
        return render_template('query_results.html', results=results)
    except Exception as e:
        return f"An error occurred: {e}", 500


@bp.route('/get_slots', methods=['GET'])
def get_slots():
    slots = []
    csv_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'filtered_slots.csv')

    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)  # Read CSV with headers
            for row in reader:
                if "Slot Name" in row and "Range Name" in row:  # Ensure expected columns exist
                    slots.append({"slot_name": row["Slot Name"], "range_name": row["Range Name"]})

        return jsonify(slots)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/graph/object/<object_name>', methods=['GET'])
def get_object_graph(object_name):
    """
    Returns RDF triples connected to a specific polymer object for Cytoscape visualization.
    """
    # --- Clean up object label ---
    # Sometimes Flask receives something like {'type': 'literal', 'value': '41149_Q1'}
    if object_name.startswith("{"):
        try:
            parsed = json.loads(object_name)
            object_name = parsed.get("value", object_name)
        except Exception:
            pass

    # --- SPARQL prefixes ---
    prefixes = """
    PREFIX iao: <http://purl.obolibrary.org/obo/iao.owl/>
    PREFIX obi: <http://purl.obolibrary.org/obo/obi.owl/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    """

    # --- SPARQL query ---
    query = f"""
    {prefixes}
    SELECT ?subject ?predicate ?object
    WHERE {{
      ?smd iao:IAO_0000136 ?obj_uri .
      ?obj_uri rdfs:label "{object_name}" .
      ?smd ?predicate ?object .
      ?smd rdf:type iao:IAO_0000032 .
      BIND(?obj_uri AS ?subject)
    }}
    """

    try:
        repo_url = f"http://localhost:7200/repositories/{current_app.config['GRAPHDB_REPO']}"
        username = current_app.config.get("GRAPHDB_USERNAME")
        password = current_app.config.get("GRAPHDB_PASSWORD")

        results = run_sparql_query(repo_url, query, username, password)

        nodes = {}
        edges = []

        for r in results:
            subj = r.get("subject", {}).get("value", "")
            pred = r.get("predicate", {}).get("value", "")
            obj = r.get("object", {}).get("value", "")

            if not subj or not obj:
                continue

            # Add subject node
            if subj not in nodes:
                nodes[subj] = {"data": {"id": subj, "label": subj}}

            # Add object node
            if obj not in nodes:
                nodes[obj] = {"data": {"id": obj, "label": obj}}

            # Add edge
            edges.append({
                "data": {
                    "source": subj,
                    "target": obj,
                    "label": pred
                }
            })

        graph_json = {"elements": {"nodes": list(nodes.values()), "edges": edges}}
        return jsonify(graph_json)

    except Exception as e:
        print(f"Graph fetch error: {e}")
        return jsonify({"error": str(e)}), 500
