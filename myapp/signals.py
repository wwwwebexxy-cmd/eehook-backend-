"""Lifecycle hooks for backend-owned welcome-bonus delivery."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, WelcomeBonus
from .welcome_bonus import (
    assign_active_welcome_bonuses_to_user,
    assign_welcome_bonus_to_existing_users,
)


@receiver(post_save, sender=WelcomeBonus)
def assign_new_welcome_bonus(sender, instance, created, **kwargs):
    if created:
        assign_welcome_bonus_to_existing_users(instance)


@receiver(post_save, sender=User)
def assign_campaigns_to_new_customer(sender, instance, created, **kwargs):
    if created:
        assign_active_welcome_bonuses_to_user(instance)
