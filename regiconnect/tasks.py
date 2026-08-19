from celery import shared_task


@shared_task(ignore_result=True)
def run_connector_job(job_id: int):
    from .runtime import execute_job

    return execute_job(job_id)
