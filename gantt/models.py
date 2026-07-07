from django.conf import settings
from django.db import models


class TaskDependency(models.Model):
    """Dependency between two tasks for Gantt scheduling."""
    TYPE_FS = 'FS'  # Finish → Start
    TYPE_FF = 'FF'  # Finish → Finish
    TYPE_SS = 'SS'  # Start → Start
    TYPE_SF = 'SF'  # Start → Finish
    TYPE_CHOICES = [
        (TYPE_FS, 'Finish → Start'),
        (TYPE_FF, 'Finish → Finish'),
        (TYPE_SS, 'Start → Start'),
        (TYPE_SF, 'Start → Finish'),
    ]

    predecessor = models.ForeignKey(
        'planner.Task',
        on_delete=models.CASCADE,
        related_name='dependency_successors',
    )
    successor = models.ForeignKey(
        'planner.Task',
        on_delete=models.CASCADE,
        related_name='dependency_predecessors',
    )
    dep_type = models.CharField(max_length=2, choices=TYPE_CHOICES, default=TYPE_FS)
    lag_days = models.SmallIntegerField(default=0)

    class Meta:
        unique_together = [['predecessor', 'successor', 'dep_type']]

    def __str__(self):
        return f'{self.predecessor_id} {self.dep_type} {self.successor_id}'
