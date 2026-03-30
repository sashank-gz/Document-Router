import argparse
import concurrent.futures
import json
import logging
import time
from pathlib import Path

import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("stress-test")

# Constants
BASE_URL = "http://127.0.0.1:8000"
NUM_REQUESTS = 10
WORKERS = 10
DUMMY_PDF_PATH = Path("test_stress.pdf")


def create_dummy_pdf():
    """Create a small dummy PDF file for testing."""
    if not DUMMY_PDF_PATH.exists():
        with open(DUMMY_PDF_PATH, "wb") as f:
            f.write(
                b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Count 0 >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
            )


def upload_file(idx):
    """Simulate a single file upload request."""
    logger.info(f"Task {idx}: Starting upload...")
    try:
        with open(DUMMY_PDF_PATH, "rb") as f:
            files = {"files": (f"stress_test_{idx}.pdf", f, "application/pdf")}
            response = requests.post(f"{BASE_URL}/upload", files=files)

        if response.status_code == 200:
            data = response.json()
            job_id = data["jobs"][0]["job_id"]
            logger.info(f"Task {idx}: Upload successful. Job ID: {job_id}")
            return job_id
        else:
            logger.error(f"Task {idx}: Upload failed with status {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Task {idx}: Error during upload: {str(e)}")
        return None


def poll_job_status(job_id, timeout=30):
    """Poll the status of a job until it's COMPLETED or FAILED."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{BASE_URL}/jobs/{job_id}")
            if response.status_code == 200:
                job = response.json()
                status = job["status"]
                if status in ["COMPLETED", "FAILED"]:
                    return status
                time.sleep(1)
            else:
                logger.error(f"Error polling job {job_id}: status {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error polling job {job_id}: {str(e)}")
            return None
    return "TIMEOUT"


def run_stress_test(num_requests, workers):
    """Run the stress test suite."""
    create_dummy_pdf()

    logger.info(f"--- Starting Stress Test ({num_requests} requests, {workers} workers) ---")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        # Step 1: Fire all uploads
        job_futures = [executor.submit(upload_file, i) for i in range(num_requests)]
        job_ids = [
            f.result()
            for f in concurrent.futures.as_completed(job_futures)
            if f.result() is not None
        ]

        logger.info(f"Successfully started {len(job_ids)} jobs.")

        # Step 2: Poll status in parallel
        status_futures = {executor.submit(poll_job_status, j_id): j_id for j_id in job_ids}

        results = {"COMPLETED": 0, "FAILED": 0, "TIMEOUT": 0, "ERRORS": 0}

        for future in concurrent.futures.as_completed(status_futures):
            j_id = status_futures[future]
            try:
                status = future.result()
                if status is None:
                    status = "ERRORS"
                results[status] = results.get(status, 0) + 1
                logger.info(f"Job {j_id} finished with status: {status}")
            except Exception as e:
                results["ERRORS"] += 1
                logger.error(f"Job {j_id} raised an error: {str(e)}")

    logger.info("--- Stress Test Results ---")
    logger.info(json.dumps(results, indent=2))

    # Check for "Database is locked" in server logs manually or by inspecting stdout
    # In a real automated test we'd capture server stderr/stdout.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate concurrent uploads against the router")
    parser.add_argument(
        "num", nargs="?", type=int, default=NUM_REQUESTS, help="Number of requests to fire"
    )
    parser.add_argument(
        "workers", nargs="?", type=int, default=WORKERS, help="Number of worker threads"
    )
    args = parser.parse_args()

    run_stress_test(args.num, args.workers)
