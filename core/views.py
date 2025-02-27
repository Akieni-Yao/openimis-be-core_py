import csv
import qrcode
import base64
from io import BytesIO
from PIL import Image
from django.conf import settings
from django.http import Http404, StreamingHttpResponse, HttpResponse
from isodate import strftime
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import InteractiveUser, User, ExportableQueryModel
from .scheduler import scheduler
from .serializers import UserSerializer
from django.utils.translation import ugettext as _


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    # If we don't specify the IsAuthenticated, the framework will look for the core.user_view permission and prevent
    # any access from non-admin users
    permission_classes = [IsAuthenticated]

    @action(detail=False)
    def current_user(self, request):
        serializer = self.get_serializer(request.user, many=False)
        return Response(serializer.data)


@api_view(['GET'])
def fetch_export(request):
    requested_export = request.query_params.get('export')
    export = ExportableQueryModel.objects.filter(name=requested_export).first()
    if not export:
        raise Http404
    elif export.user != request.user:
        raise PermissionDenied({"message": _("Only user requesting export can fetch request")})
    elif export.is_deleted:
        return Response(data='Export csv file was removed from server.', status=status.HTTP_410_GONE)

    export_file_name = F"export_{export.model}_{strftime(export.create_date, '%d/%m/%Y')}.csv"
    return StreamingHttpResponse(
        (row for row in export.content.file.readlines()),
        content_type="text/csv",
        headers={'Content-Disposition': F'attachment; filename="{export_file_name}"'},
    )


def _serialize_job(job):
    return "name: %s, trigger: %s, next run: %s, handler: %s" % (
        job.name, job.trigger, job.next_run_time, job.func)


@api_view(['GET'])
def get_scheduled_jobs(request):
    return Response([_serialize_job(job) for job in scheduler.get_jobs()])


@api_view(['GET'])
def force_verify_user(request):
    if not request.query_params.get('user_id'):
        return Response({"message": "User ID is required"}, status=status.HTTP_400_BAD_REQUEST)
    i_user = InteractiveUser.objects.filter(
        validity_to__isnull=True, user__id=request.query_params.get('user_id')
    ).first()
    if not i_user:
        return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    if i_user:
        i_user.is_verified = True
        i_user.save()
    return Response({"message": "User verified"}, status=status.HTTP_200_OK)

@api_view(['GET'])
def force_un_verify_user(request):
    if not request.query_params.get('user_id'):
        return Response({"message": "User ID is required"}, status=status.HTTP_400_BAD_REQUEST)
    i_user = InteractiveUser.objects.filter(
        validity_to__isnull=True, user__id=request.query_params.get('user_id')
    ).first()
    if not i_user:
        return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    if i_user:
        i_user.is_verified = False
        i_user.save()
    return Response({"message": "User unverified"}, status=status.HTTP_200_OK)
    
    
@api_view(['POST'])
def generate_qr(request):

    data = request.data.get('input')
    qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_L,
    box_size=10,
    border=4,
    )
    qr.add_data(data)
    qr = qrcode.make()
    stream = BytesIO()
    qr_pil = Image(qr, format="PNG")
    image_data = qr_pil.save(stream, format="PNG")
    # image_data.seek(0) # set BytesIO pointer to the begining
    img_binary=base64.b64encode(image_data.getvalue()).decode('utf-8')

    return Response({"qr": img_binary}, status=status.HTTP_201_CREATED)
