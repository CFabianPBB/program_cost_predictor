import os
import json
import openai
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Set your OpenAI API key from an environment variable
openai.api_key = os.environ.get("OPENAI_API_KEY")
print("DEBUG: OpenAI API Key:", openai.api_key)  # Debug print - ensure your key is not None

# Global variables to hold the data from the uploaded file
program_inventory = []
personnel_costs = []
non_personnel_costs = []

# ----------------------------
# Fallback Equal Allocation Function
# ----------------------------
def allocate_percentages(num_items):
    """
    Allocate 100% among num_items in increments of 5%.
    Returns a list of allocations (each in percentage).
    """
    if num_items == 0:
        return []
    total_increments = 20  # 100 / 5 = 20 increments
    base = total_increments // num_items
    remainder = total_increments % num_items
    allocations = [base * 5 for _ in range(num_items)]
    for i in range(remainder):
        allocations[i] += 5
    return allocations

# ----------------------------
# GPT Allocation Helper Functions
# ----------------------------
def get_personnel_allocation_from_gpt(position, programs):
    """
    Use GPT to get an allocation for a personnel position.
    Returns a dictionary mapping program names to allocation percentages.
    """
    program_names = [p["Program Name"] for p in programs]

    prompt = f"""
You are an expert in organizational management and program planning. Consider the following details:

- Department: {position["Department"]}
- Position Title: {position["Position Name"]}
- Programs in Department: {program_names}

Based on the responsibilities typically associated with this position, please allocate the position's 100% work time among these programs.
The allocation must:
- Be in increments of 5% (e.g., 5%, 10%, 15%, etc.)
- Sum exactly to 100%
- Only allocate to at most {len(program_names)} programs

Provide the result as a JSON object mapping each program to its allocation percentage. For example:
{{
  "Budget Analysis": 40,
  "Financial Planning": 40,
  "Audit": 20
}}

Use your best judgement to reflect the likelihood of this position supporting these programs.
"""
    try:
        response = openai.Chat.create(
            model="gpt-4",  # If you don't have GPT-4 access, use "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "You are an expert in cost allocation."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150,
        )
        content = response.choices[0].message.content.strip()

        # Debug print to see the raw GPT response
        print(f"\n--- GPT response for position '{position['Position Name']}':\n{content}\n---\n")

        allocation = json.loads(content)

        # Validate that the allocations sum to 100
        total_allocation = sum(allocation.values())
        if total_allocation != 100:
            raise ValueError(f"Allocations do not sum to 100 (sum={total_allocation}).")

        return allocation

    except Exception as e:
        print(f"GPT error for personnel allocation ({position['Position Name']}): {e}")
        # Fallback: use equal allocation
        num_programs = len(program_names)
        equal_alloc = allocate_percentages(num_programs)
        return {name: alloc for name, alloc in zip(program_names, equal_alloc)}

def get_non_personnel_allocation_from_gpt(item, programs):
    """
    Use GPT to get an allocation for a non-personnel cost item.
    Returns a dictionary mapping program names to allocation percentages.
    """
    program_names = [p["Program Name"] for p in programs]

    prompt = f"""
You are an expert in budgeting and cost allocation. Consider the following details:

- Department: {item["Department"]}
- Line Item: {item["Line Item"]}
- Programs in Department: {program_names}

Please allocate the cost of the "{item["Line Item"]}" among these programs in a way that reflects how the expense would likely be distributed.
The allocation must:
- Be in increments of 5% (e.g., 5%, 10%, 15%, etc.)
- Sum exactly to 100%

Provide the result as a JSON object mapping each program to its allocation percentage. For example:
{{
  "Budget Analysis": 30,
  "Financial Planning": 50,
  "Audit": 20
}}

Use your best judgement to reflect typical usage patterns in the department.
"""
    try:
        response = openai.Chat.create(
            model="gpt-4",  # If you don't have GPT-4 access, use "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "You are an expert in cost allocation."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150,
        )
        content = response.choices[0].message.content.strip()

        # Debug print to see the raw GPT response
        print(f"\n--- GPT response for line item '{item['Line Item']}':\n{content}\n---\n")

        allocation = json.loads(content)

        total_allocation = sum(allocation.values())
        if total_allocation != 100:
            raise ValueError(f"Allocations do not sum to 100 (sum={total_allocation}).")

        return allocation

    except Exception as e:
        print(f"GPT error for non-personnel allocation ({item['Line Item']}): {e}")
        num_programs = len(program_names)
        equal_alloc = allocate_percentages(num_programs)
        return {name: alloc for name, alloc in zip(program_names, equal_alloc)}

# ----------------------------
# Generate Allocations & Summary
# ----------------------------
def generate_allocations():
    personnel_allocations = []
    non_personnel_allocations = []
    summary = {}

    # Process personnel positions using GPT
    for position in personnel_costs:
        dept = position["Department"]
        # Get programs for this department (limit to 10 if necessary)
        dept_programs = [p for p in program_inventory if p["Department"] == dept]
        if len(dept_programs) > 10:
            dept_programs = dept_programs[:10]

        # Get GPT allocation for this position
        alloc_dict = get_personnel_allocation_from_gpt(position, dept_programs)

        for prog in dept_programs:
            prog_name = prog["Program Name"]
            alloc_percent = alloc_dict.get(prog_name, 0)
            allocated_cost = position["Cost"] * alloc_percent / 100
            fte = alloc_percent / 100
            personnel_allocations.append({
                "Department": dept,
                "Program Name": prog_name,
                "Position Name": position["Position Name"],
                "Allocation": alloc_percent,
                "Cost": allocated_cost,
                "FTE": fte
            })
            # Update program summary
            if prog_name not in summary:
                summary[prog_name] = {"personnel_cost": 0, "non_personnel_cost": 0, "FTE": 0}
            summary[prog_name]["personnel_cost"] += allocated_cost
            summary[prog_name]["FTE"] += fte

    # Process non-personnel cost items using GPT
    for item in non_personnel_costs:
        dept = item["Department"]
        dept_programs = [p for p in program_inventory if p["Department"] == dept]
        if len(dept_programs) > 10:
            dept_programs = dept_programs[:10]

        alloc_dict = get_non_personnel_allocation_from_gpt(item, dept_programs)

        for prog in dept_programs:
            prog_name = prog["Program Name"]
            alloc_percent = alloc_dict.get(prog_name, 0)
            allocated_cost = item["Cost"] * alloc_percent / 100
            non_personnel_allocations.append({
                "Department": dept,
                "Program Name": prog_name,
                "Line Item": item["Line Item"],
                "Allocation": alloc_percent,
                "Cost": allocated_cost
            })
            # Update program summary
            if prog_name not in summary:
                summary[prog_name] = {"personnel_cost": 0, "non_personnel_cost": 0, "FTE": 0}
            summary[prog_name]["non_personnel_cost"] += allocated_cost

    # Finalize summary: calculate total cost per program
    for prog in summary:
        summary[prog]["total_cost"] = summary[prog]["personnel_cost"] + summary[prog]["non_personnel_cost"]

    return personnel_allocations, non_personnel_allocations, summary

# ----------------------------
# Flask Routes
# ----------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    # Retrieve the uploaded Excel file
    file = request.files.get('excel_file')
    if file:
        try:
            # Read the Excel file with all sheets
            sheets = pd.read_excel(file, sheet_name=None)
            
            # Expecting sheet names: "Program Inventory", "Personnel Costs", "Non-Personnel Costs"
            global program_inventory, personnel_costs, non_personnel_costs
            if "Program Inventory" in sheets:
                program_inventory = sheets["Program Inventory"].to_dict(orient="records")
            else:
                return "Error: 'Program Inventory' tab not found.", 400
            
            if "Personnel Costs" in sheets:
                personnel_costs = sheets["Personnel Costs"].to_dict(orient="records")
            else:
                return "Error: 'Personnel Costs' tab not found.", 400
            
            if "Non-Personnel Costs" in sheets:
                non_personnel_costs = sheets["Non-Personnel Costs"].to_dict(orient="records")
            else:
                return "Error: 'Non-Personnel Costs' tab not found.", 400
            
            return redirect(url_for('results'))
        except Exception as e:
            return f"Error processing file: {e}", 500
    else:
        return "No file uploaded", 400

@app.route('/results')
def results():
    personnel_allocations, non_personnel_allocations, summary = generate_allocations()
    return render_template('results.html',
                           personnel_allocations=personnel_allocations,
                           non_personnel_allocations=non_personnel_allocations,
                           summary=summary)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

