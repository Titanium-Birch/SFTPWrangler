from io import BytesIO
import json
from typing import Any, Dict


class SameJsonPayload:
    """Utility matcher for boto3-stubs to compare BytesIO instances with json
    payload.
    """
    def __init__(self, expected_data: BytesIO):
        self.expected_data = expected_data

    def __eq__(self, other):
        if not isinstance(other, BytesIO):
            return False
        
        def compare_json_values(obj_a: Dict[str, Any], obj_b: Dict[str, Any]):
            for key in obj_a.keys():
                if key in obj_b:
                    value_a = obj_a[key]
                    value_b = obj_b[key]
                    
                    if isinstance(value_a, dict) and isinstance(value_b, dict):
                        if not compare_json_values(value_a, value_b):
                            return False
                    else:
                        if str(value_a) != str(value_b):
                            return False
                else:
                    return False

            for key in obj_b.keys():
                if key not in obj_a:
                    return False

            return True
        
        json_a = json.loads(self.expected_data.getvalue())
        json_b = json.loads(other.getvalue())

        return compare_json_values(obj_a=json_a, obj_b=json_b)

    def __repr__(self):
        return f"<_io.BytesIO object wrapping different json payload>"