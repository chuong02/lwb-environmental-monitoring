from django.urls import path
from . import views

urlpatterns = [
    path('health/', views.health, name='mobile-health'),
    path('nodes/', views.node_list, name='mobile-nodes'),
    path('nodes/status-summary/', views.summary, name='mobile-summary'),
    path('nodes/<int:node_id>/latest/', views.latest, name='mobile-latest'),
    path('nodes/<int:node_id>/history/', views.history, name='mobile-history'),
]
