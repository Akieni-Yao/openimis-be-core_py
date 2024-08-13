import base64

from core.constants import *
from core.models import CamuNotification
from core.notification_message import *
from core.services.userServices import find_approvers


def base64_encode(input_string):
    bytes_string = input_string.encode('utf-8')
    encoded_bytes = base64.b64encode(bytes_string)
    encoded_string = encoded_bytes.decode('utf-8')
    return encoded_string


class NotificationService:
    @staticmethod
    def create_notification(user, module, message, redirect_url, portal_redirect_url):
        notification = CamuNotification.objects.create(
            user=user,
            module=module,
            message=message,
            redirect_url=redirect_url,
            portal_redirect_url=portal_redirect_url
        )
        return notification

    @staticmethod
    def notify_users(users, module, message, redirect_url, portal_redirect_url):
        for user in users:
            NotificationService.create_notification(user, module, message, redirect_url, portal_redirect_url)


def ph_created(policy_holder):
    try:
        if not policy_holder or not hasattr(policy_holder, 'id') or not policy_holder.id:
            raise ValueError("Invalid Policy Holder object or missing ID.")
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")
        message = policy_holder_status_messages.get('PH_STATUS_CREATED', None)
        redirect_url = f"/policyHolders/policyHolder/{policy_holder.id}"
        NotificationService.notify_users(approvers, "Policy Holder", message, redirect_url, None)
    except Exception as e:
        print(f"Error in policy_holder_created: {e}")


def penalty_created(penalty_object):
    try:
        if not penalty_object or not hasattr(penalty_object, 'id') or not penalty_object.id:
            raise ValueError("Invalid penalty object or missing ID.")
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")
        message = penalty_status_messages.get('PENALTY_NOT_PAID', None)
        id_string = f"PaymentPenaltyAndSanctionType:{penalty_object.id}"
        encoded_str = base64_encode(id_string)
        if not encoded_str:
            raise ValueError("Failed to encode penalty ID.")
        redirect_url = f"/payment/paymentpenalty/overview/{encoded_str}"
        NotificationService.notify_users(approvers, "Penalty", message, redirect_url, None)

    except Exception as e:
        print(f"Error in penalty_created: {e}")


def contract_created(contract_object):
    try:
        if not contract_object or not hasattr(contract_object, 'id'):
            raise ValueError("Invalid contract object or missing ID.")
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")
        message = contract_status_messages.get('STATE_DRAFT', None)
        contract_id = contract_object.id if contract_object.id else ''
        redirect_url = f"/contracts/contract/{contract_id}"
        NotificationService.notify_users(approvers, "Contract", message, redirect_url, 'penalty_created')
    except Exception as e:
        print(f"Error in contract_created: {e}")


def pa_req_created(pa_req_object):
    try:
        if not pa_req_object or not hasattr(pa_req_object, 'id'):
            raise ValueError("Invalid contract object or missing ID.")
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")
        message = pre_auth_req_status_messages.get('PA_CREATED', None)
        pa_req_id = pa_req_object.id if pa_req_object.id else ''
        redirect_url = f"/claim/healthFacilities/preauthorizationForm/{pa_req_id}"
        NotificationService.notify_users(approvers, "Claim", message, redirect_url, None)
    except Exception as e:
        print(f"Error in contract_created: {e}")


def contract_submitted(contract_object):
    approvers = find_approvers()
    message = contract_status_messages.get('STATE_EXECUTABLE', None)
    redirect_url = f"/policyholder/{contract_object.id}/details/"
    NotificationService.notify_users(approvers, "Contract", message, redirect_url, None)


def payment_created(payment_obj):
    try:
        if not payment_obj or not hasattr(payment_obj, 'id') or not payment_obj.id:
            raise ValueError("Invalid Payment object or missing ID.")
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")
        message = contract_payment_status_messages.get('STATUS_CREATED', None)
        redirect_url = f"/payment/overview/{payment_obj.id}"
        portal_redirect_url = f"/paymentform/:id={payment_obj.id}"
        NotificationService.notify_users(approvers, "Payment", message, redirect_url, portal_redirect_url)
    except Exception as e:
        print(f"Error in payment_created: {e}")

def payment_updated(payment_obj):
    try:
        if not payment_obj or not hasattr(payment_obj, 'id') or not payment_obj.id:
            raise ValueError("Invalid Payment object or missing ID.")
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")
        payment_status = payment_obj.status
        if payment_status == 1:
            msg = "STATUS_CREATED"
        elif payment_status == 2:
            msg = "STATUS_PENDING"
        elif payment_status == 3:
            msg = "STATUS_PROCESSING"
        elif payment_status == 4:
            msg = "STATUS_OVERDUE"
        elif payment_status == 5:
            msg = "STATUS_APPROVED"
        else:
            msg = "STATUS_REJECTED"
        message = contract_payment_status_messages.get(msg, None)
        redirect_url = f"/payment/overview/{payment_obj.id}"
        portal_redirect_url = f"/paymentform/:id={payment_obj.id}"
        NotificationService.notify_users(approvers, "Payment", message, redirect_url, portal_redirect_url)
    except Exception as e:
        print(f"Error in payment_created: {e}")


def fosa_created(fosa_obj):
    try:
        if not fosa_obj or not hasattr(fosa_obj, 'id') or not fosa_obj.id:
            raise ValueError("Invalid FOSA object or missing ID.")
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")
        message = fosa_status_messages.get('FOSA_STATUS_CREATED', None)
        redirect_url = f"/location/healthFacility/{fosa_obj.id}"
        NotificationService.notify_users(approvers, "Location", message, redirect_url, None)
    except Exception as e:
        print(f"Error in fosa_created: {e}")


def claim_created(claim_obj):
    try:
        if not claim_obj or not hasattr(claim_obj, 'id') or not claim_obj.id:
            raise ValueError("Invalid Claim object or missing ID.")
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")
        message = claim_status_messages.get('STATUS_CREATED', None)
        redirect_url = f"/claim/healthFacilities/claim/{claim_obj.id}"
        NotificationService.notify_users(approvers, "Claim", message, redirect_url, None)
    except Exception as e:
        print(f"Error in claim_created: {e}")


def claim_updated(claim_obj):
    try:
        if not claim_obj or not hasattr(claim_obj, 'id') or not claim_obj.id:
            raise ValueError("Invalid Claim object or missing ID.")
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")
        claim_status = claim_obj.status
        if claim_status == 1:
            msg = "STATUS_REJECTED"
        elif claim_status == 2:
            msg = "STATUS_ENTERED"
        elif claim_status == 4:
            msg = "STATUS_CHECKED"
        elif claim_status == 8:
            msg = "STATUS_PROCESSED"
        elif claim_status == 16:
            msg = "STATUS_VALUATED"
        elif claim_status == 32:
            msg = "STATUS_REWORK"
        elif claim_status == 64:
            msg = "STATUS_PAID"
        message = claim_status_messages.get(msg, None)
        redirect_url = f"/claim/healthFacilities/claim/{claim_obj.id}"
        NotificationService.notify_users(approvers, "Claim", message, redirect_url, None)
    except Exception as e:
        print(f"Error in claim_created: {e}")

def create_camu_notification(notification_type, object):
    if notification_type == POLICYHOLDER_CREATION_NT:
        ph_created(object)
    elif notification_type == CONTRACT_CREATION_NT:
        contract_created(object)
    elif notification_type == PAYMENT_CREATION_NT:
        payment_created(object)
    elif notification_type == PENALTY_CREATION_NT:
        penalty_created(object)
    elif notification_type == FOSA_CREATION_NT:
        fosa_created(object)
    elif notification_type == CLAIM_CREATION_NT:
        claim_created(object)
    elif notification_type == PA_REQ_CREATION_NT:
        pa_req_created(object)
    else:
        return None
