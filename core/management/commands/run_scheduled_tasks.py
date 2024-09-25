from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import ScheduledTask, CronJobLog

class Command(BaseCommand):
    help = 'Runs scheduled tasks based on their frequency and logs execution details'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        tasks = ScheduledTask.objects.filter(is_completed=False)

        for task in tasks:
            if self.should_run_task(task, now):
                # Implement your cron job logic here
                try:
                    output = self.run_task_logic(task)  # Logic for the task, returns output

                    # Log success
                    CronJobLog.objects.create(
                        task=task,
                        status='success',
                        output=output
                    )

                    # Reschedule for the next run
                    self.reschedule_task(task)

                except Exception as e:
                    # Log failure with error message
                    CronJobLog.objects.create(
                        task=task,
                        status='failed',
                        error=str(e)
                    )

    def should_run_task(self, task, now):
        # Check if the task should run based on its schedule (same as before)
        if task.frequency == 'monthly':
            return now.day == task.day_of_month and now.hour == task.hour_of_day
        if task.frequency == 'weekly':
            return now.weekday() == task.day_of_week and now.hour == task.hour_of_day
        if task.frequency == 'daily':
            return now.hour == task.hour_of_day
        return False

    def run_task_logic(self, task):
        """
        Placeholder for the actual cron job logic. You can replace this with the logic 
        that needs to be executed for each cron job.
        """
        print(f"Running task: {task.task_name}")
        # Example output
        return f"{task.task_name} executed successfully at {timezone.now()}"

    def reschedule_task(self, task):
        """
        Reschedules the task based on its frequency.
        """
        if task.frequency == 'monthly':
            task.run_at += timedelta(days=30)  # Simplified logic for next month
        elif task.frequency == 'weekly':
            task.run_at += timedelta(weeks=1)  # Run again after a week
        elif task.frequency == 'daily':
            task.run_at += timedelta(days=1)   # Run again the next day
        task.is_completed = False
        task.save()