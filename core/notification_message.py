# Policy Holder Status Messages
policy_holder_status_messages = {
    'PH_STATUS_CREATED': {
        'en': 'Policy Holder Created {policy_holder_code}',
        'fr': 'Policy Holder Created {policy_holder_code}'
    },
    'PH_STATUS_PENDING': {
        'en': 'Policy Holder Pending {policy_holder_code}',
        'fr': 'Policy Holder Pending {policy_holder_code}'
    },
    'PH_STATUS_APPROVED': {
        'en': 'Policy Holder Approved {policy_holder_code}',
        'fr': 'Policy Holder Approved {policy_holder_code}'
    },
    'PH_STATUS_REJECTED': {
        'en': 'Policy Holder Rejected {policy_holder_code}',
        'fr': 'Policy Holder Rejected {policy_holder_code}'
    },
    'PH_STATUS_REWORK': {
        'en': 'Policy Holder Rework {policy_holder_code}',
        'fr': 'Policy Holder Rework {policy_holder_code}'
    }
}

# FOSA Status Messages
fosa_status_messages = {
    'FOSA_STATUS_CREATED': {
        'en': 'FOSA Created {fosa_code}',
        'fr': 'FOSA Created {fosa_code}'
    }
}

# Insuree Status Messages
insuree_status_messages = {
    'PH_INS_CREATED': {
        'en': 'Insuree Created {chf_id} for Policy Holder {policy_holder_code}',
        'fr': 'Insuree Created {chf_id} for Policy Holder {policy_holder_code}'
    },
    'PRE_REGISTERED': {
        'en': 'Insuree Created {chf_id}',
        'fr': 'Insuree Created {chf_id}'
    },
    'APPROVED': {
        'en': 'Insuree Status Changed: Approved {chf_id}',
        'fr': 'Insuree Status Changed: Approved {chf_id}'
    },
    'WAITING_FOR_DOCUMENT_AND_BIOMETRIC': {
        'en': 'Insuree Status Changed: Waiting for Document and Biometric {chf_id}',
        'fr': 'Insuree Status Changed: Waiting for Document and Biometric {chf_id}'
    },
    'WAITING_FOR_DOCUMENT': {
        'en': 'Insuree Status Changed: Waiting for Document {chf_id}',
        'fr': 'Insuree Status Changed: Waiting for Document {chf_id}'
    },
    'WAITING_FOR_BIOMETRIC': {
        'en': 'Insuree Status Changed: Waiting for Biometric {chf_id}',
        'fr': 'Insuree Status Changed: Waiting for Biometric {chf_id}'
    },
    'WAITING_FOR_APPROVAL': {
        'en': 'Insuree Status Changed: Waiting for Approval {chf_id}',
        'fr': 'Insuree Status Changed: Waiting for Approval {chf_id}'
    },
    'WAITING_FOR_QUEUE': {
        'en': 'Insuree Status Changed: Waiting in Queue {chf_id}',
        'fr': 'Insuree Status Changed: Waiting in Queue {chf_id}'
    },
    'ACTIVE': {
        'en': 'Insuree Status Changed: Active {chf_id}',
        'fr': 'Insuree Status Changed: Active {chf_id}'
    },
    'REJECTED': {
        'en': 'Insuree Status Changed: Rejected {chf_id}',
        'fr': 'Insuree Status Changed: Rejected {chf_id}'
    },
    'REWORK': {
        'en': 'Insuree Status Changed: Rework Required {chf_id}',
        'fr': 'Insuree Status Changed: Rework Required {chf_id}'
    },
    'ON_HOLD': {
        'en': 'Insuree Status Changed: On Hold {chf_id}',
        'fr': 'Insuree Status Changed: On Hold {chf_id}'
    },
    'END_OF_LIFE': {
        'en': 'Insuree Status Changed: End of Life {chf_id}',
        'fr': 'Insuree Status Changed: End of Life {chf_id}'
    },
    'NOT_ACTIVE': {
        'en': 'Insuree Status Changed: Not Active {chf_id}',
        'fr': 'Insuree Status Changed: Not Active {chf_id}'
    }
}

# Contract Status Messages
contract_status_messages = {
    'STATE_DRAFT': {
        'en': 'Contract Created {contract_code}',
        'fr': 'Contract Created {contract_code}'
    },
    'STATE_NEGOTIABLE': {
        'en': 'Contract Submitted {contract_code}',
        'fr': 'Contract Submitted {contract_code}'
    },
    'STATE_EXECUTABLE': {
        'en': 'Contract Approved {contract_code}',
        'fr': 'Contract Approved {contract_code}'
    },
    'STATE_COUNTER': {
        'en': 'Contract Rejected {contract_code}',
        'fr': 'Contract Rejected {contract_code}'
    },
    'STATE_TERMINATED': {
        'en': 'Contract Terminated {contract_code}',
        'fr': 'Contract Terminated {contract_code}'
    },
    'STATE_DISPUTED': {
        'en': 'Contract Disputed {contract_code}',
        'fr': 'Contract Disputed {contract_code}'
    },
    'STATE_EXECUTED': {
        'en': 'Contract Executed {contract_code}',
        'fr': 'Contract Executed {contract_code}'
    }
}

# Contract Payment Status Messages
contract_payment_status_messages = {
    'STATUS_CREATED': {
        'en': 'Contract Payment Created {payment_code}',
        'fr': 'Contract Payment Created {payment_code}'
    },
    'STATUS_PENDING': {
        'en': 'Contract Payment Pending {payment_code}',
        'fr': 'Contract Payment Pending {payment_code}'
    },
    'STATUS_PROCESSING': {
        'en': 'Contract Payment Processing {payment_code}',
        'fr': 'Contract Payment Processing {payment_code}'
    },
    'STATUS_OVERDUE': {
        'en': 'Contract Payment Overdue {payment_code}',
        'fr': 'Contract Payment Overdue {payment_code}'
    },
    'STATUS_APPROVED': {
        'en': 'Contract Payment Approved {payment_code}',
        'fr': 'Contract Payment Approved {payment_code}'
    },
    'STATUS_REJECTED': {
        'en': 'Contract Payment Rejected {payment_code}',
        'fr': 'Contract Payment Rejected {payment_code}'
    }
}

# Penalty Status Messages
penalty_status_messages = {
    'PENALTY_NOT_PAID': {
        'en': 'Penalty Not Paid {penalty_code}',
        'fr': 'Penalty Not Paid {penalty_code}'
    },
    'PENALTY_OUTSTANDING': {
        'en': 'Penalty Outstanding {penalty_code}',
        'fr': 'Penalty Outstanding {penalty_code}'
    },
    'PENALTY_PAID': {
        'en': 'Penalty Paid {penalty_code}',
        'fr': 'Penalty Paid {penalty_code}'
    },
    'PENALTY_CANCELED': {
        'en': 'Penalty Canceled {penalty_code}',
        'fr': 'Penalty Canceled {penalty_code}'
    },
    'PENALTY_REDUCED': {
        'en': 'Penalty Reduced {penalty_code}',
        'fr': 'Penalty Reduced {penalty_code}'
    },
    'PENALTY_PROCESSING': {
        'en': 'Penalty Processing {penalty_code}',
        'fr': 'Penalty Processing {penalty_code}'
    },
    'PENALTY_APPROVED': {
        'en': 'Penalty Approved {penalty_code}',
        'fr': 'Penalty Approved {penalty_code}'
    },
    'PENALTY_REJECTED': {
        'en': 'Penalty Rejected {penalty_code}',
        'fr': 'Penalty Rejected {penalty_code}'
    },
    'REDUCE_REJECTED': {
        'en': 'Reduction Rejected {penalty_code}',
        'fr': 'Reduction Rejected {penalty_code}'
    },
    'REDUCE_APPROVED': {
        'en': 'Reduction Approved {penalty_code}',
        'fr': 'Reduction Approved {penalty_code}'
    }
}

# Claim Status Messages
claim_status_messages = {
    'STATUS_CREATED': {
        'en': 'Claim Created {claim_code}',
        'fr': 'Claim Created {claim_code}'
    },
    'STATUS_REJECTED': {
        'en': 'Claim Rejected {claim_code}',
        'fr': 'Claim Rejected {claim_code}'
    },
    'STATUS_ENTERED': {
        'en': 'Claim Entered {claim_code}',
        'fr': 'Claim Entered {claim_code}'
    },
    'STATUS_CHECKED': {
        'en': 'Claim Submitted {claim_code}',
        'fr': 'Claim Submitted {claim_code}'
    },
    'STATUS_PROCESSED': {
        'en': 'Claim Processed {claim_code}',
        'fr': 'Claim Processed {claim_code}'
    },
    'STATUS_VALUATED': {
        'en': 'Claim Approved {claim_code}',
        'fr': 'Claim Approved {claim_code}'
    },
    'STATUS_REWORK': {
        'en': 'Claim Rework {claim_code}',
        'fr': 'Claim Rework {claim_code}'
    },
    'STATUS_PAID': {
        'en': 'Claim Paid {claim_code}',
        'fr': 'Claim Paid {claim_code}'
    }
}

# Prior Authorization Request Status Messages
pre_auth_req_status_messages = {
    'PA_REJECTED': {
        'en': 'Prior Authorization Request Rejected {auth_code}',
        'fr': 'Prior Authorization Request Rejected {auth_code}'
    },
    'PA_CREATED': {
        'en': 'Prior Authorization Request Created {auth_code}',
        'fr': 'Prior Authorization Request Created {auth_code}'
    },
    'PA_WAITING_FOR_APPROVAL': {
        'en': 'Prior Authorization Request Waiting for Approval {auth_code}',
        'fr': 'Prior Authorization Request Waiting for Approval {auth_code}'
    },
    'PA_REWORK': {
        'en': 'Prior Authorization Request Rework {auth_code}',
        'fr': 'Prior Authorization Request Rework {auth_code}'
    },
    'PA_APPROVED': {
        'en': 'Prior Authorization Request Approved {auth_code}',
        'fr': 'Prior Authorization Request Approved {auth_code}'
    }
}
