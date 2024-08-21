import base64
import logging

from contract.models import Contract
from claim.models import Claim, PreAuthorization
from core.constants import *
from core.models import CamuNotification
from core.notification_message import *
from core.services.userServices import find_approvers
from payment.models import Payment, PaymentPenaltyAndSanction

logger = logging.getLogger(__name__)


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
        # Validate the policy_holder object and ID
        if not policy_holder or not hasattr(policy_holder, 'id') or not policy_holder.id:
            raise ValueError("Invalid Policy Holder object or missing ID.")

        # Find approvers
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")

        # Retrieve the message template and format the messages
        message_template = policy_holder_status_messages.get('PH_STATUS_CREATED', None)
        if not message_template:
            raise ValueError("Message template not found for PH_STATUS_CREATED.")

        message_en = message_template['en'].format(policy_holder_code=policy_holder.code)
        message_fr = message_template['fr'].format(policy_holder_code=policy_holder.code)
        message = {
            'en': message_en,
            'fr': message_fr
        }

        # Construct the redirect URL
        redirect_url = f"/policyHolders/policyHolder/{policy_holder.id}"

        # Notify the users
        NotificationService.notify_users(approvers, "Policy Holder", message, redirect_url, None)
        logging.info(f"Notification sent successfully for Policy Holder ID {policy_holder.id}.")

    except Exception as e:
        logging.error(f"Error in policy_holder_created: {e}", exc_info=True)


def ph_insuree_added(ph_insuree):
    policy_holder = ph_insuree.policy_holder
    insuree = ph_insuree.insuree
    try:
        # Validate the policy_holder object and ID
        if not policy_holder or not hasattr(policy_holder, 'id') or not policy_holder.id:
            raise ValueError("Invalid Policy Holder object or missing ID.")
        # Validate the insuree object and ID
        if not insuree or not hasattr(insuree, 'id') or not insuree.id:
            raise ValueError("Invalid Insuree object or missing ID.")

        # Find approvers
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")

        # Retrieve the message template and format the messages
        message_template = insuree_status_messages.get('PH_INS_CREATED', None)
        if not message_template:
            raise ValueError("Message template not found for PH_STATUS_CREATED.")

        message_en = message_template['en'].format(chf_id=insuree.chf_id, policy_holder_code=policy_holder.code)
        message_fr = message_template['fr'].format(chf_id=insuree.chf_id, policy_holder_code=policy_holder.code)
        message = {
            'en': message_en,
            'fr': message_fr
        }

        # Construct the redirect URL
        redirect_url = f"/insuree/insurees/insuree/{insuree.id}"

        # Notify the users
        NotificationService.notify_users(approvers, "Policy Holder", message, redirect_url, None)
        logging.info(f"Notification sent successfully for Policy Holder ID {policy_holder.id}.")
        logging.info(f"Notification sent successfully for Insuree ID {insuree.id}.")

    except Exception as e:
        logging.error(f"Error in policy_holder_created: {e}", exc_info=True)


def insuree_added(insuree):
    try:
        # Validate the insuree object and ID
        if not insuree or not hasattr(insuree, 'id') or not insuree.id:
            raise ValueError("Invalid Insuree object or missing ID.")

        # Find approvers
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")

        # Retrieve the message template and format the messages
        message_template = insuree_status_messages.get('INS_CREATED', None)
        if not message_template:
            raise ValueError("Message template not found for INS_CREATED.")

        message_en = message_template['en'].format(chf_id=insuree.chf_id, )
        message_fr = message_template['fr'].format(chf_id=insuree.chf_id, )
        message = {
            'en': message_en,
            'fr': message_fr
        }

        # Construct the redirect URL
        redirect_url = f"/insuree/insurees/insuree/{insuree.id}"

        # Notify the users
        NotificationService.notify_users(approvers, "Insuree", message, redirect_url, None)
        logging.info(f"Notification sent successfully for Insuree ID {insuree.id}.")

    except Exception as e:
        logging.error(f"Error in policy_holder_created: {e}", exc_info=True)


# def insuree_updated(insuree):
#     try:
#         # Validate the insuree object and ID
#         if not insuree or not hasattr(insuree, 'id') or not insuree.id:
#             raise ValueError("Invalid Insuree object or missing ID.")
#
#         # Find approvers
#         approvers = find_approvers()
#         if not approvers:
#             raise ValueError("No approvers found.")
#
#         status = insuree.status
#
#         # Retrieve the message template and format the messages
#         message_template = insuree_status_messages.get('INS_CREATED', None)
#         if not message_template:
#             raise ValueError("Message template not found for INS_CREATED.")
#
#         message_en = message_template['en'].format(chf_id=insuree.chf_id, )
#         message_fr = message_template['fr'].format(chf_id=insuree.chf_id, )
#         message = {
#             'en': message_en,
#             'fr': message_fr
#         }
#
#         # Construct the redirect URL
#         redirect_url = f"/insuree/insurees/insuree/{insuree.id}"
#
#         # Notify the users
#         NotificationService.notify_users(approvers, "Insuree", message, redirect_url, None)
#         logging.info(f"Notification sent successfully for Insuree ID {insuree.id}.")
#
#     except Exception as e:
#         logging.error(f"Error in policy_holder_created: {e}", exc_info=True)
#
#
# def ph_updated(policy_holder):
#     try:
#         # Validate the policy_holder object and ID
#         if not policy_holder or not hasattr(policy_holder, 'id') or not policy_holder.id:
#             raise ValueError("Invalid Policy Holder object or missing ID.")

        # Find approvers
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")

        # Retrieve the message template and format the messages
        message_template = policy_holder_status_messages.get('PH_STATUS_CREATED', None)
        if not message_template:
            raise ValueError("Message template not found for PH_STATUS_CREATED.")

        message_en = message_template['en'].format(policy_holder_code=policy_holder.code)
        message_fr = message_template['fr'].format(policy_holder_code=policy_holder.code)
        message = {
            'en': message_en,
            'fr': message_fr
        }

        # Construct the redirect URL
        redirect_url = f"/policyHolders/policyHolder/{policy_holder.id}"

        # Notify the users
        NotificationService.notify_users(approvers, "Policy Holder", message, redirect_url, None)
        logging.info(f"Notification sent successfully for Policy Holder ID {policy_holder.id}.")

    except Exception as e:
        logging.error(f"Error in policy_holder_created: {e}", exc_info=True)


def penalty_created(penalty_object):
    try:
        # Validate the penalty_object
        if not penalty_object or not hasattr(penalty_object, 'id') or not penalty_object.id:
            raise ValueError("Invalid penalty object or missing ID.")

        # Find approvers
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")

        # Retrieve the message template and format the messages
        message_template = penalty_status_messages.get('PENALTY_NOT_PAID', None)
        if not message_template:
            raise ValueError("Message template not found for PENALTY_NOT_PAID.")

        message_en = message_template['en'].format(penalty_code=penalty_object.code)
        message_fr = message_template['fr'].format(penalty_code=penalty_object.code)
        message = {
            'en': message_en,
            'fr': message_fr
        }

        # Encode penalty ID and construct redirect URL
        id_string = f"PaymentPenaltyAndSanctionType:{penalty_object.id}"
        encoded_str = base64_encode(id_string)
        if not encoded_str:
            raise ValueError("Failed to encode penalty ID.")

        redirect_url = f"/payment/paymentpenalty/overview/{encoded_str}"

        # Notify users
        NotificationService.notify_users(approvers, "Penalty", message, redirect_url, None)

        # Log successful notification
        logging.info(f"Notification sent successfully for Penalty ID {penalty_object.id}.")

    except Exception as e:
        # Log the exception with traceback
        logging.error(f"Error in penalty_created: {e}", exc_info=True)


def penalty_updated(penalty_object):
    try:
        # Validate the penalty_object
        if not penalty_object or not hasattr(penalty_object, 'id') or not penalty_object.id:
            raise ValueError("Invalid penalty object or missing ID.")

        # Find approvers
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")
        status = penalty_object.status
        msg = None
        if status == PaymentPenaltyAndSanction.PENALTY_NOT_PAID:
            msg = 'PENALTY_NOT_PAID'
        if status == PaymentPenaltyAndSanction.PENALTY_OUTSTANDING:
            msg = 'PENALTY_OUTSTANDING'
        if status == PaymentPenaltyAndSanction.PENALTY_PAID:
            msg = 'PENALTY_PAID'
        if status == PaymentPenaltyAndSanction.PENALTY_CANCELED:
            msg = 'PENALTY_CANCELED'
        if status == PaymentPenaltyAndSanction.PENALTY_REDUCED:
            msg = 'PENALTY_REDUCED'
        if status == PaymentPenaltyAndSanction.PENALTY_PROCESSING:
            msg = 'PENALTY_PROCESSING'
        if status == PaymentPenaltyAndSanction.PENALTY_APPROVED:
            msg = 'PENALTY_APPROVED'
        if status == PaymentPenaltyAndSanction.PENALTY_REJECTED:
            msg = 'PENALTY_REJECTED'
        if status == PaymentPenaltyAndSanction.REDUCE_REJECTED:
            msg = 'REDUCE_REJECTED'
        if status == PaymentPenaltyAndSanction.REDUCE_APPROVED:
            msg = 'REDUCE_APPROVED'

        # Retrieve the message template and format the messages
        message_template = penalty_status_messages.get(msg, None)
        if not message_template:
            raise ValueError("Message template not found for PENALTY_NOT_PAID.")

        message_en = message_template['en'].format(penalty_code=penalty_object.code)
        message_fr = message_template['fr'].format(penalty_code=penalty_object.code)
        message = {
            'en': message_en,
            'fr': message_fr
        }

        # Encode penalty ID and construct redirect URL
        id_string = f"PaymentPenaltyAndSanctionType:{penalty_object.id}"
        encoded_str = base64_encode(id_string)
        if not encoded_str:
            raise ValueError("Failed to encode penalty ID.")

        redirect_url = f"/payment/paymentpenalty/overview/{encoded_str}"

        # Notify users
        NotificationService.notify_users(approvers, "Penalty", message, redirect_url, None)

        # Log successful notification
        logging.info(f"Notification sent successfully for Penalty ID {penalty_object.id}.")

    except Exception as e:
        # Log the exception with traceback
        logging.error(f"Error in penalty_created: {e}", exc_info=True)


def contract_created(contract_object):
    try:
        # Validate the contract_object
        if not contract_object or not hasattr(contract_object, 'id') or not hasattr(contract_object, 'code'):
            raise ValueError("Invalid contract object or missing ID/code.")

        # Find approvers
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")

        # Retrieve the message template and format the message
        message_template = contract_status_messages.get('STATE_DRAFT', None)
        if not message_template:
            raise ValueError("Message template not found for STATE_DRAFT.")

        # Format the message with the contract_code
        message = {
            'en': message_template['en'].format(contract_code=contract_object.code),
            'fr': message_template['fr'].format(contract_code=contract_object.code)
        }

        # Construct the redirect URL
        contract_id = contract_object.id if contract_object.id else ''
        redirect_url = f"/contracts/contract/{contract_id}"
        portal_redirect_url = f"/contract/:id={contract_id}"

        # Notify users
        NotificationService.notify_users(approvers, "Contract", message, redirect_url, portal_redirect_url)

        # Log successful notification
        logging.info(f"Notification sent successfully for Contract Code {contract_object.code}.")

    except Exception as e:
        # Log the exception with traceback
        logging.error(f"Error in contract_created: {e}", exc_info=True)


def contract_updated(contract_object):
    try:
        # Validate the contract_object
        if not contract_object or not hasattr(contract_object, 'id') or not hasattr(contract_object, 'code'):
            raise ValueError("Invalid contract object or missing ID/code.")

        # Find approvers
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")

        contract_status = contract_object.status
        if contract_status == Contract.STATE_NEGOTIABLE:
            msg = "STATE_NEGOTIABLE"
        elif contract_status == Contract.STATE_EXECUTABLE:
            msg = "STATE_EXECUTABLE"
        elif contract_status == Contract.STATE_COUNTER:
            msg = "STATE_COUNTER"
        elif contract_status == Contract.STATE_TERMINATED:
            msg = "STATE_TERMINATED"
        elif contract_status == Contract.STATE_DISPUTED:
            msg = "STATE_DISPUTED"
        elif contract_status == Contract.STATE_EXECUTED:
            msg = "STATE_EXECUTED"

        # Retrieve the message template and format the message
        message_template = contract_status_messages.get(msg, None)
        if not message_template:
            raise ValueError("Message template not found for STATE_DRAFT.")

        # Format the message with the contract_code
        message = {
            'en': message_template['en'].format(contract_code=contract_object.code),
            'fr': message_template['fr'].format(contract_code=contract_object.code)
        }

        # Construct the redirect URL
        contract_id = contract_object.id if contract_object.id else ''
        redirect_url = f"/contracts/contract/{contract_id}"
        portal_redirect_url = f"/contract/:id={contract_id}"

        # Notify users
        NotificationService.notify_users(approvers, "Contract", message, redirect_url, portal_redirect_url)

        # Log successful notification
        logging.info(f"Notification sent successfully for Contract Code {contract_object.code}.")

    except Exception as e:
        # Log the exception with traceback
        logging.error(f"Error in contract_created: {e}", exc_info=True)


def pa_req_created(pa_req_object):
    try:
        # Validate the pa_req_object
        if not pa_req_object or not hasattr(pa_req_object, 'id') or not hasattr(pa_req_object, 'code'):
            raise ValueError("Invalid Prior Authorization Request object or missing ID/code.")

        # Find approvers
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")

        # Retrieve the message template and format the message
        message_template = pre_auth_req_status_messages.get('PA_CREATED', None)
        if not message_template:
            raise ValueError("Message template not found for PA_CREATED.")

        # Format the message with the auth_code
        message = {
            'en': message_template['en'].format(auth_code=pa_req_object.code),
            'fr': message_template['fr'].format(auth_code=pa_req_object.code)
        }
        # Encode penalty ID and construct redirect URL
        id_string = f"PreAuthorizationType:{pa_req_object.id}"
        encoded_str = base64_encode(id_string)
        if not encoded_str:
            raise ValueError("Failed to encode Pre Authorization ID.")
        # Construct the redirect URL
        pa_req_id = pa_req_object.id if pa_req_object.id else ''
        redirect_url = f"/claim/healthFacilities/preauthorizationForm/{pa_req_id}"
        portal_redirect_url = f"/autharizationForm/:id={id_string}"
        # Notify users
        NotificationService.notify_users(approvers, "Claim", message, redirect_url, portal_redirect_url)

        # Log successful notification
        logging.info(f"Notification sent successfully for Prior Authorization Request Code {pa_req_object.code}.")

    except Exception as e:
        # Log the exception with traceback
        logging.error(f"Error in pa_req_created: {e}", exc_info=True)


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

        # Retrieve the message template and format the message
        message_template = contract_payment_status_messages.get('STATUS_CREATED', None)
        if not message_template:
            raise ValueError("Message template not found for PA_CREATED.")

        # Format the message with the auth_code
        message = {
            'en': message_template['en'].format(auth_code=payment_obj.code),
            'fr': message_template['fr'].format(auth_code=payment_obj.code)
        }

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
        if payment_status == Payment.STATUS_CREATED:
            msg = "STATUS_CREATED"
        elif payment_status == Payment.STATUS_PENDING:
            msg = "STATUS_PENDING"
        elif payment_status == Payment.STATUS_PROCESSING:
            msg = "STATUS_PROCESSING"
        elif payment_status == Payment.STATUS_OVERDUE:
            msg = "STATUS_OVERDUE"
        elif payment_status == Payment.STATUS_APPROVED:
            msg = "STATUS_APPROVED"
        else:
            msg = "STATUS_REJECTED"

        # Retrieve the message template and format the message
        message_template = contract_payment_status_messages.get(msg, None)
        if not message_template:
            raise ValueError("Message template not found for PA_CREATED.")

        # Format the message with the auth_code
        message = {
            'en': message_template['en'].format(auth_code=payment_obj.code),
            'fr': message_template['fr'].format(auth_code=payment_obj.code)
        }

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

        # Retrieve the message template and format the message
        message_template = fosa_status_messages.get('FOSA_STATUS_CREATED', None)
        if not message_template:
            raise ValueError("Message template not found for PA_CREATED.")

        # Format the message with the auth_code
        message = {
            'en': message_template['en'].format(auth_code=fosa_obj.code),
            'fr': message_template['fr'].format(auth_code=fosa_obj.code)
        }

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

        # Retrieve the message template and format the message
        message_template = claim_status_messages.get('STATUS_CREATED', None)
        if not message_template:
            raise ValueError("Message template not found for PA_CREATED.")

        # Format the message with the auth_code
        message = {
            'en': message_template['en'].format(auth_code=claim_obj.code),
            'fr': message_template['fr'].format(auth_code=claim_obj.code)
        }
        redirect_url = f"/claim/healthFacilities/claim/{claim_obj.id}"
        portal_redirect_url = f"/claimForm/:id={claim_obj.id}"
        NotificationService.notify_users(approvers, "Claim", message, redirect_url, portal_redirect_url)
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
        if claim_status == Claim.STATUS_REJECTED:
            msg = "STATUS_REJECTED"
        elif claim_status == Claim.STATUS_ENTERED:
            msg = "STATUS_ENTERED"
        elif claim_status == Claim.STATUS_CHECKED:
            msg = "STATUS_CHECKED"
        elif claim_status == Claim.STATUS_PROCESSED:
            msg = "STATUS_PROCESSED"
        elif claim_status == Claim.STATUS_VALUATED:
            msg = "STATUS_VALUATED"
        elif claim_status == Claim.STATUS_REWORK:
            msg = "STATUS_REWORK"
        elif claim_status == Claim.STATUS_PAID:
            msg = "STATUS_PAID"

        # Retrieve the message template and format the message
        message_template = claim_status_messages.get(msg, None)
        if not message_template:
            raise ValueError("Message template not found for PA_CREATED.")

        # Format the message with the auth_code
        message = {
            'en': message_template['en'].format(auth_code=claim_obj.code),
            'fr': message_template['fr'].format(auth_code=claim_obj.code)
        }
        redirect_url = f"/claim/healthFacilities/claim/{claim_obj.id}"
        portal_redirect_url = f"/claimForm/:id={claim_obj.id}"
        NotificationService.notify_users(approvers, "Claim", message, redirect_url, portal_redirect_url)
    except Exception as e:
        print(f"Error in claim_created: {e}")


def pa_req_updated(pa_req_object):
    try:
        # Validate the pa_req_object
        if not pa_req_object or not hasattr(pa_req_object, 'id') or not hasattr(pa_req_object, 'code'):
            raise ValueError("Invalid Prior Authorization Request object or missing ID/code.")

        # Find approvers
        approvers = find_approvers()
        if not approvers:
            raise ValueError("No approvers found.")

        status = pa_req_object.status
        msg = None
        if status == PreAuthorization.PA_REJECTED:
            msg = 'PA_REJECTED'
        elif status == PreAuthorization.PA_CREATED:
            msg = 'PA_CREATED'
        elif status == PreAuthorization.PA_WAITING_FOR_APPROVAL:
            msg = 'PA_WAITING_FOR_APPROVAL'
        elif status == PreAuthorization.PA_REWORK:
            msg = 'PA_REWORK'
        elif status == PreAuthorization.PA_APPROVED:
            msg = 'PA_APPROVED'

        message_template = claim_status_messages.get(msg, None)
        if not message_template:
            raise ValueError(f"Message template not found for {msg}.")

        # Format the message with the auth_code
        message = {
            'en': message_template['en'].format(auth_code=pa_req_object.code),
            'fr': message_template['fr'].format(auth_code=pa_req_object.code)
        }
        # Encode penalty ID and construct redirect URL
        id_string = f"PreAuthorizationType:{pa_req_object.id}"
        encoded_str = base64_encode(id_string)
        if not encoded_str:
            raise ValueError("Failed to encode Pre Authorization ID.")
        # Construct the redirect URL
        pa_req_id = pa_req_object.id if pa_req_object.id else ''
        redirect_url = f"/claim/healthFacilities/preauthorizationForm/{pa_req_id}"
        portal_redirect_url = f"/autharizationForm/:id={id_string}"
        # Notify users
        NotificationService.notify_users(approvers, "Claim", message, redirect_url, portal_redirect_url)

        # Log successful notification
        logging.info(f"Notification sent successfully for Prior Authorization Request Code {pa_req_object.code}.")

    except Exception as e:
        # Log the exception with traceback
        logging.error(f"Error in pa_req_created: {e}", exc_info=True)


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
    elif notification_type == POLICYHOLDER_UPDATE_NT:
        ph_updated(object)
    elif notification_type == CONTRACT_UPDATE_NT:
        contract_updated(object)
        pass
    elif notification_type == PAYMENT_UPDATE_NT:
        payment_updated(object)
    elif notification_type == PENALTY_UPDATE_NT:
        penalty_updated(object)
    elif notification_type == CLAIM_UPDATE_NT:
        claim_updated(object)
    elif notification_type == PA_REQ_UPDATE_NT:
        pa_req_updated(object)
    else:
        return None
