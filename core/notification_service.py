import base64

from django.conf import settings

from core.models import CamuNotification
from core.notification_message import penalty_notify_message
from core.services.userServices import find_approvers


def base64_encode(input_string):
    bytes_string = input_string.encode('utf-8')
    encoded_bytes = base64.b64encode(bytes_string)
    encoded_string = encoded_bytes.decode('utf-8')
    return encoded_string


class NotificationService:
    @staticmethod
    def create_notification(user, module, message, redirect_url, notification_type):
        notification = CamuNotification.objects.create(
            user=user,
            module=module,
            message=message,
            redirect_url=redirect_url,
            notification_type=notification_type
        )
        NotificationService.dispatch(notification)
        return notification

    @staticmethod
    def dispatch(notification):
        pass

    @staticmethod
    def notify_users(users, module, message, redirect_url, notification_type):
        for user in users:
            NotificationService.create_notification(user, module, message, redirect_url, notification_type)


def penalty_created(penalty_object):
    try:
        if not penalty_object or not hasattr(penalty_object, 'id') or not penalty_object.id:
            raise ValueError("Invalid penalty object or missing ID.")

        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")

        message = penalty_notify_message.get('penalty_create', None)

        id_string = f"PaymentPenaltyAndSanctionType:{penalty_object.id}"
        encoded_str = base64_encode(id_string)
        if not encoded_str:
            raise ValueError("Failed to encode penalty ID.")

        redirect_url = f"/payment/paymentpenalty/overview/{encoded_str}"
        NotificationService.notify_users(approvers, "Penalty", message, redirect_url, 'penalty_created')

    except Exception as e:
        print(f"Error in penalty_created: {e}")


def contract_created(contract_object):
    try:
        if not contract_object or not hasattr(contract_object, 'id'):
            raise ValueError("Invalid contract object or missing ID.")
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")
        message = penalty_notify_message
        contract_id = contract_object.id if contract_object.id else ''
        redirect_url = f"/contracts/contract/{contract_id}"
        NotificationService.notify_users(approvers, "Penalty", message, redirect_url, 'penalty_created')
    except Exception as e:
        print(f"Error in contract_created: {e}")


def contract_submitted(contract_object):
    approvers = find_approvers()
    message = penalty_notify_message
    redirect_url = f"/policyholder/{contract_object.id}/details/"
    NotificationService.notify_users(approvers, "Penalty", message, redirect_url, 'penalty_created')


def create_camu_notification(notification_type, object):
    if notification_type == 'penalty_created':
        penalty_created(object)
    elif notification_type == 'contract_created':
        contract_created(object)
    else:
        pass
