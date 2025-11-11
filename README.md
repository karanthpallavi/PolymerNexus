PolymerNexus – Workflow for Semantification of Polymer Datasets and Query Interface for Polymer Data
Version: 1.0
Technology Stack: Flask · GraphDB (RDF store) · SPARQL · HTML5 · JavaScript · SHACL · YAML · LinkML
1. Overview
PolymerNexus is a web-based knowledge system designed to integrate, visualize, and query complex polymer characterization data through an intuitive, SPARQL-free interface.
The platform automates the creation, querying of a semantic knowledge graph built on Ontology, and SHACL based validation. It enables industry professionals to explore structure–property–processing relationships in polymers without needing to know RDF or SPARQL syntax.
2. Core Objectives
•	Knowledge Representation: Transform raw polymer data into OWL-based knowledge graph using ontologies such as IAO, OBI, and BFO, PMDCo3, DIGITRUBBER.
•	Intuitive Querying: Provide a user-friendly query form so that materials experts can search data by properties (e.g., Mooney Stress Relaxation, Hardness mean value, Vinyl Content, etc.) without writing SPARQL.
•	Precision Filtering: Support multi-property comparison queries (e.g., find samples with hardness > 60 and Mooney viscosity < 35).
•	Scalable Integration: Designed for deployment in R&D environments to support data analytics and insights generation, which can further include visual exploration of the Knowledge Graph
3. System Architecture
3.1 Components
Layer	Technology	Purpose
Frontend	HTML5, CSS3, JavaScript	Interactive forms 
Backend	Flask (Python)	REST endpoints, query generation, and rendering
Triple Store	GraphDB	RDF storage and SPARQL endpoint
Ontology Base	PMDCo3, DIGITRUBBER	Semantic schema and reasoning layer

3.2 Architecture Diagram
 
4. Key Functionalities
4.1 Data Ingestion and Graph Construction
•	Raw CSV or experimental datasets are parsed and semantically annotated.
•	Entities such as Polymer, Measurement Datum, Quality, and Value Specification are represented using ontology classes, which are guided by SHACL Shapes.
•	Relationships like measuredQualityOf and hasValueSpecification are established using the SHACL Shapes.
•	Output is serialized as OWL in turtle format and uploaded to GraphDB.
4.2 Intelligent Query Interface
The /query page provides guided templates for domain-specific searches:
a) Single Property Filter
Find polymers where a given property satisfies a numeric condition (e.g., Hardness > 50).
b) Multi-Property Comparison
Find objects satisfying multiple property criteria simultaneously, including:
•	Greater / Less conditions
•	Automatic validation and range handling
•	Tolerance for numeric “equals” filters
c) Maximum Value Query
Return polymers that exhibit the highest measured value for a specific property.
d)	Minimum Value Query
Return polymers that exhibit the lowest measured value for a specific property.
________________________________________
4.3 Dynamic Query Generation
Without requiring SPARQL knowledge, user selections are mapped internally to SPARQL templates.
For example:
SELECT ?object ?quality ?numericvalue WHERE {
  ?smd rdf:type iao:IAO_0000032 ;
       iao:IAO_0000221 ?quality_uri ;
       iao:IAO_0000136 ?object_uri ;
       obi:OBI_0001938 ?valuespec .
  ?valuespec obi:OBI_0001937 ?numericvalue .
  ?object_uri rdfs:label ?object .
  ?quality_uri rdfs:label ?quality .
  FILTER(xsd:double(?numericvalue) >= 48.0 && xsd:double(?numericvalue) <= 50.0)
}
This query is fully auto-generated from dropdown inputs.
________________________________________
4.4 Result Visualization and Exploration
•	Results are shown in a sortable data table.
•	Users can return to the query form or download the query results as a csv or excel file.
________________________________________
5. User Experience (UX) Highlights
•	 Dropdown selection of polymer properties (mapped to RDF labels)
•	Choice of numeric comparison operators: greater, less, equals, within range
•	Automatic validation and error handling
•	“Back to Query” navigation for rapid iteration
•	Configurable connection to on-premise or remote GraphDB repositories
________________________________________


6. Technical Design Details
Component	Description
routes.py	Handles web routes, form inputs, SPARQL query construction, GraphDB interaction, and result rendering.
query_form.html	Provides a modular UI for selecting query templates and properties.
query_results.html	Displays query results 
run.py	Application entry point for local deployment.
config.py	Repository connection settings (GraphDB URL, credentials, etc.).
________________________________________
7. Example Future Use Cases
Use Case	Description	Example
Material Screening	Find polymers with specific mechanical or chemical profiles	“Show polymers with Mooney viscosity between 30–40 and hardness above 60”
Process Optimization	Identify correlations between rheological and thermal properties	“Compare S50 and Glass Transition Temperature”
Benchmarking	Retrieve highest performing polymer for a given property	“Find sample with maximum Elastic Modulus”
Knowledge Exploration	Visualize inter-property relationships across experiments	“Show relationships of Mooney Stress Relaxation for all compounds”
________________________________________
8. Deployment & Configuration
Local Setup
# Clone repository
git clone https://github.com/<org>/PolymerNexus.git
cd PolymerNexus

# Setup virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure GraphDB in config.py
GRAPHDB_REPO = "ArlanxeoPolymers"
GRAPHDB_URL = "http://localhost:7200"
Run Application
python run.py
Then visit: http://127.0.0.1:5000/query
________________________________________
9. Security and Access Control
•	User access to GraphDB endpoints can be secured using credentials in environment variables.
•	Optional role-based access control can be integrated via Flask-Login for multi-user deployments.
________________________________________
10. Future Enhancements
Feature	Description
Ontology-based auto-suggestion	Suggest related properties based on semantic hierarchy.
Property correlation analytics	Scatter plots or heat maps for multi-property trends.
Batch query execution	Upload property ranges from CSV and auto-generate reports.
Natural language querying	Use NLP to convert human questions to SPARQL templates.
Graph Export	Export result graphs in GraphML or JSON-LD for reuse.
________________________________________
11. Impact
By bridging domain expertise and semantic data technologies, PolymerNexus empowers polymer scientists to:
•	Reduce manual data retrieval effort
•	Gain faster insights from experimental results
•	Enable ontology-based data sharing across R&D sites
•	Lay groundwork for AI-ready polymer design systems
________________________________________
12. Contacts and Acknowledgements
Project: PolymerNexus
Maintainers: Dr. Pallavi Karanth and Dr. Lars Vogt 
Contact: [pallavi.karanth@tib.eu]
Acknowledgements:
InSuKa Project – BMBF: 13XP5196F

