"""6. Reported & estimated salaries, 7. behaviour without salary data."""
from app.models import SalaryBenchmark, SalaryDataset
from app.pipeline.salary import apply_salary, jalali_year
from tests.fixtures import pages
from tests.helpers import jobinja_raw, put


def senior_devops(db, code, salary="توافقی", city="تهران ، تهران"):
    return put(db, "jobinja", jobinja_raw(code=code, title="Senior DevOps Engineer", salary=salary, location=city,
                                          experience="پنج تا ده سال", description_html=pages.DEVOPS_DESCRIPTION)).job


def test_reported_salary(db):
    job = senior_devops(db, "r1", salary="۵۰ - ۷۰ میلیون تومان")
    assert job.salary_status == "reported"
    assert (job.effective_salary_min, job.effective_salary_max) == (50_000_000, 70_000_000)
    assert job.salary_estimate["confidence"] == 1.0


def test_unknown_without_data_is_not_low(db):
    job = senior_devops(db, "u1")
    assert job.salary_status == "unknown"
    assert job.effective_salary_min is None and job.effective_salary_max is None
    assert "پایین" in job.salary_estimate["note"]  # explicit: missing != low


def test_estimate_from_dataset(db):
    ds = SalaryDataset(name="test-dataset", version=1, source_name="داده آزمایشی (نه واقعی)", data_year=jalali_year(),
                       is_active=True, row_count=1)
    db.add(ds)
    db.flush()
    db.add(SalaryBenchmark(dataset_id=ds.id, category="devops", seniority="senior", city="تهران",
                           salary_min=60_000_000, salary_max=90_000_000, salary_median=75_000_000, sample_size=40))
    db.commit()
    job = senior_devops(db, "e1")
    assert job.seniority == "senior"
    assert job.salary_status == "estimated"
    est = job.salary_estimate
    assert est["method"] == "benchmark_dataset" and est["data_year"] == jalali_year()
    assert est["sample_size"] == 40 and 0 < est["confidence"] <= 0.8
    assert (job.effective_salary_min, job.effective_salary_max) == (60_000_000, 90_000_000)


def test_inactive_dataset_not_used(db):
    ds = SalaryDataset(name="old", version=1, source_name="x", data_year=1400, is_active=False, row_count=1)
    db.add(ds)
    db.flush()
    db.add(SalaryBenchmark(dataset_id=ds.id, category="devops", seniority="senior", salary_min=1, salary_max=2))
    db.commit()
    assert senior_devops(db, "i1").salary_status == "unknown"


def test_estimate_from_collected_reported_salaries(db):
    for i, (lo, hi) in enumerate([(40, 60), (50, 70), (55, 75), (60, 80), (45, 65)]):
        senior_devops(db, f"m{i}", salary=f"{lo} - {hi} میلیون تومان")
    job = senior_devops(db, "target")
    apply_salary(db, job)
    db.commit()
    est = job.salary_estimate
    assert job.salary_status == "estimated"
    assert est["method"] == "collected_reported_salaries" and est["sample_size"] == 5
    assert est["min"] <= est["median"] <= est["max"]


def test_too_few_samples_stays_unknown(db):
    for i in range(3):
        senior_devops(db, f"f{i}", salary="50 - 70 میلیون تومان")
    job = senior_devops(db, "target2")
    assert job.salary_status == "unknown"
