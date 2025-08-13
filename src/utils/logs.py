import logging
import os
import re
from typing import Optional

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def redacted_ssh_private_key(potential_private_key: Optional[str]) -> str:
    """Anonymizes given private key value.

    Args:
        potential_private_key (Optional[str]): a str value that potentially contains a private key

    Returns:
        str: the anonymized private key
    """
    begin_pattern = re.compile(r"^-----BEGIN .*PRIVATE KEY-----")
    end_pattern = re.compile(r"^-----END .*PRIVATE KEY-----")
    return __redacted_ssh_private_key(
        potential_private_key=potential_private_key, begin_pattern=begin_pattern, end_pattern=end_pattern
    )


def redacted_pgp_private_key(potential_private_key: Optional[str]) -> str:
    """Anonymizes given private key value.

    Args:
        potential_private_key (Optional[str]): a str value that potentially contains a pgp private key

    Returns:
        str: the anonymized pgp private key
    """
    begin_pattern = re.compile(r"^-----BEGIN PGP PRIVATE KEY BLOCK-----")
    end_pattern = re.compile(r"^-----END PGP PRIVATE KEY BLOCK-----")
    return __redacted_ssh_private_key(
        potential_private_key=potential_private_key, begin_pattern=begin_pattern, end_pattern=end_pattern
    )


def __redacted_ssh_private_key(potential_private_key: Optional[str], begin_pattern: re.Pattern[str],
                               end_pattern: re.Pattern[str]) -> str:
    if not potential_private_key:
        return ""    

    match = re.search(begin_pattern, potential_private_key)
    if match:
        obfuscated_lines = []

        lines = potential_private_key.split("\n")
        obfuscate_next_line = False

        for line in lines:
            if begin_pattern.match(line):
                obfuscated_lines.append(line)
            elif end_pattern.match(line):
                obfuscated_lines.append(line)
                obfuscate_next_line = False
            else:
                if obfuscate_next_line:
                    obfuscated_lines.append("*" * (len(line) - 1) + line[-1])
                elif len(line) > 0:
                    obfuscated_lines.append(line[0] + "*" * (len(line) - 1))
                obfuscate_next_line = True
        
        obfuscated_key = "\n".join(obfuscated_lines)
        return obfuscated_key
    
    if len(potential_private_key) > 4:
        return potential_private_key[:2] + "*" * (len(potential_private_key) - 4) + potential_private_key[-2:]
    else:
        return potential_private_key
