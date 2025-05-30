from django.urls import re_path
from api.consumers import ChatConsumer


websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<room_id>[a-f0-9\-]+)/$', ChatConsumer.as_asgi()),
]