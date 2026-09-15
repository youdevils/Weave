from celery import shared_task


@shared_task
def test_celery():
    return "Celery is working"
