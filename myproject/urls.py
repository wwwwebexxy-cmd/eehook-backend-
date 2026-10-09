from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [

    path( "nested_admin/", include( "nested_admin.urls" ) ),

    path("",include("myapp.urls")),

    # Keep the dashboard management API's /admin/manage/* routes ahead of
    # Django Admin's catch-all /admin/ resolver.
    path( "admin/", admin.site.urls ),
    
    path("payment/", include("payment.urls")),

] + static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT
)
