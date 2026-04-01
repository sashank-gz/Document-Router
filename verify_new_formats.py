import asyncio
import shutil
import zipfile
from pathlib import Path

# Set up paths
BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)


async def test_all():

    from app.file_utils import FileCategory, get_file_category
    from app.models import JobStore
    from app.router_engine import DocumentRouterEngine

    # 1. Test Category Mapping
    assert get_file_category("test.png") == FileCategory.IMAGE
    assert get_file_category("test.xlsm") == FileCategory.SPREADSHEET
    assert get_file_category("test.zip") == FileCategory.ARCHIVE
    print("✓ Category mapping test passed")

    # 2. Setup mock data
    test_img = BASE_DIR / "test_image.png"
    test_img.write_text("dummy image content")

    test_zip = BASE_DIR / "test_archive.zip"
    with zipfile.ZipFile(test_zip, "w") as z:
        z.writestr("inner_pdf.pdf", "dummy pdf")
        z.writestr("inner_img.png", "dummy img")

    # 3. Test ZIP extraction logic
    job_store = JobStore(BASE_DIR / "test_jobs.db")
    job_store.initialize()

    PROCESSED_DIR = BASE_DIR / "processed"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    engine = DocumentRouterEngine(
        job_store=job_store, uploads_dir=UPLOADS_DIR, processed_dir=PROCESSED_DIR
    )

    print(f"Testing ZIP: {test_zip}")
    # Process the ZIP file
    # Note: This will try to call Docling, which might fail if models aren't loaded,
    # but we care about the SPAWNING logic here.
    job_id = job_store.create_job(file_name=test_zip.name, route="UNKNOWN", status="UPLOADED")
    try:
        # We manually call _process_file to avoid the API overhead
        engine._process_file(job_id, test_zip)
    except Exception as e:
        print(f"Extraction failed as expected (Docling mock/dummy content): {e}")

    # Check if child jobs were created
    jobs = job_store.list_jobs()
    child_jobs = [j for j in jobs if j.parent_job_id == job_id]

    print(f"Total jobs: {len(jobs)}")
    print(f"Child jobs spawned: {len(child_jobs)}")
    for cj in child_jobs:
        print(f"  - Child Job ID {cj.job_id}: {cj.file_name}")

    assert len(child_jobs) == 2, f"Expected 2 child jobs, got {len(child_jobs)}"
    print("✓ ZIP extraction and child job spawning test passed")

    # Cleanup
    if test_zip.exists():
        test_zip.unlink()
    if test_img.exists():
        test_img.unlink()
    if (BASE_DIR / "test_jobs.db").exists():
        (BASE_DIR / "test_jobs.db").unlink()

    # Clean up extraction subdirectories
    for d in UPLOADS_DIR.glob("extracted_*"):
        if d.is_dir():
            shutil.rmtree(d)


if __name__ == "__main__":
    asyncio.run(test_all())
