import pdfplumber
import config
import json
import models
import sys
import time
from llm_client import primary_client

def extract_text_from_pdf(pdf_path):
    """
    Extracts text from a given PDF file.

    Args:
        pdf_path (str): The file path to the PDF resume.

    Returns:
        str: The extracted text content from the PDF.
    """
    print(f"Extracting text from: {pdf_path}")
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Extract the visible text
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
            
            # Extract embedded hyperlinks which are not captured by extract_text()
            if page.hyperlinks:
                for link in page.hyperlinks:
                    uri = link.get("uri")
                    if uri:
                        text += f"Embedded Link: {uri}\n"
    return text

def parse_resume_with_ai(resume_text):
    """
    Send resume text to an AI model and get structured information back.
    
    Args:
        resume_text (str): The plain text extracted from the resume
        
    Returns:
        str: JSON string of structured resume information
    """
    print("Processing resume with AI model...")

    prompt = f"""Extract and return the structured resume information from the text below. 
    Only use what is explicitly stated in the text and do not infer or invent any details.
    
    CRITICAL: If any information is missing or not available in the text, use "NA" for that field. 
    This applies to all fields (e.g., summary, dates, location, links, etc.). 
    Do NOT leave fields empty or use empty strings.

    Resume text:
    {resume_text}
    """

    response_text = primary_client.generate_content(
        prompt=prompt,
        response_format=models.Resume,
    )
    return response_text

def replace_empty_with_na(data):
    """
    Recursively replaces empty strings or None values in a dictionary or list with "NA".
    """
    if isinstance(data, dict):
        return {k: replace_empty_with_na(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace_empty_with_na(i) for i in data]
    elif data == "" or data is None:
        return "NA"
    return data

def parse_and_validate_resume(resume_text, max_retries=config.MAX_RETRIES):
    """
    Attempts to parse resume text with AI, with retry logic for JSON errors or empty responses.
    
    Args:
        resume_text (str): The extracted text from the resume.
        max_retries (int): Maximum number of attempts.
        
    Returns:
        dict: The structured resume data with empty values replaced by "NA".
    """
    for attempt in range(max_retries):
        parsed_resume_details_str = parse_resume_with_ai(resume_text)
        
        if not parsed_resume_details_str:
            print(f"Attempt {attempt + 1}: Received empty response from AI. Retrying...")
            time.sleep(config.RETRY_DELAY_SECONDS)
            continue
            
        try:
            resume_data_dict = json.loads(parsed_resume_details_str)
            return replace_empty_with_na(resume_data_dict)
        except json.JSONDecodeError as e:
            print(f"Attempt {attempt + 1}: JSON decode error: {e}. Retrying...")
            time.sleep(config.RETRY_DELAY_SECONDS)
            
    print(f"ERROR: Failed to parse resume after {max_retries} attempts.")
    sys.exit(1)

def main():
    """
    Main function to orchestrate the resume parsing process.
    Downloads the resume PDF from Supabase Storage, parses it with AI, 
    and saves the structured data to both local file and Supabase DB.
    """
    import io
    import os
    import supabase_utils

    pdf_file_path = "./resume.pdf"

    # 1. Try to download resume PDF from Supabase Storage
    pdf_bytes = supabase_utils.download_resume_from_storage("resume.pdf")

    if pdf_bytes:
        print("Successfully downloaded resume.pdf from Supabase Storage.")
        # Write to a temporary local file for pdfplumber
        with open(pdf_file_path, 'wb') as f:
            f.write(pdf_bytes)
    elif os.path.exists(pdf_file_path):
        print(f"Supabase Storage download failed. Using local file: {pdf_file_path}")
    else:
        print("ERROR: Could not find resume.pdf in Supabase Storage or locally.")
        print("Please upload your resume.pdf to the 'resumes' bucket in your Supabase Storage dashboard.")
        return

    # 2. Extract text from PDF
    resume_text = extract_text_from_pdf(pdf_file_path)
    if not resume_text:
        print("Failed to extract text. Exiting.")
        return

    # 3. Parse resume text with AI
    resume_data_dict = parse_and_validate_resume(resume_text)

    # 4. Save parsed data to Supabase base_resume table
    save_success = supabase_utils.save_base_resume(resume_data_dict)
    if save_success:
        print("Successfully saved parsed resume to Supabase database.")
    else:
        print("WARNING: Failed to save parsed resume to Supabase database.")

    # 5. Also save to local JSON file (for development/fallback)
    output_path = config.BASE_RESUME_PATH
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(resume_data_dict, f, indent=4)
        print(f"Successfully saved parsed resume to local file: {output_path}")
    except Exception as e:
        print(f"Error saving resume to {output_path}: {e}")

    # 6. Clean up the temporary PDF file (don't leave sensitive data on disk in CI)
    if pdf_bytes and os.path.exists(pdf_file_path):
        try:
            os.remove(pdf_file_path)
            print(f"Cleaned up temporary file: {pdf_file_path}")
        except Exception as e:
            print(f"Warning: Could not clean up {pdf_file_path}: {e}")

    print("\nResume processing finished.")


if __name__ == "__main__":
    print("Starting resume processing...")
    main()