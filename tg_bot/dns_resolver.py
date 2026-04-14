import dns.resolver
import dns.exception
from typing import List, Tuple
from config import DNS_TIMEOUT, DNS_SERVER


async def resolve_domain(domain: str) -> Tuple[List[str], List[str]]:
    """
    Resolve domain to IPv4 and IPv6 addresses.
    Returns: (ipv4_list, ipv6_list, errors)
    """
    ipv4_list = []
    ipv6_list = []
    errors = []
    
    resolver = dns.resolver.Resolver()
    resolver.nameservers = [DNS_SERVER]
    resolver.timeout = DNS_TIMEOUT
    resolver.lifetime = DNS_TIMEOUT
    
    # Clean domain from wildcards
    clean_domain = domain.lstrip("*.")
    
    # Resolve IPv4
    try:
        answers = resolver.resolve(clean_domain, "A")
        ipv4_list = [str(rdata) for rdata in answers]
    except dns.exception.NXDOMAIN:
        errors.append(f"Domain not found: {clean_domain}")
    except dns.exception.Timeout:
        errors.append(f"DNS timeout for {clean_domain}")
    except dns.exception.DNSException as e:
        errors.append(f"DNS error: {str(e)}")
    
    # Resolve IPv6
    try:
        answers = resolver.resolve(clean_domain, "AAAA")
        ipv6_list = [str(rdata) for rdata in answers]
    except dns.exception.NXDOMAIN:
        pass  # IPv6 might not exist
    except dns.exception.Timeout:
        pass
    except dns.exception.DNSException:
        pass  # IPv6 might not exist
    
    return ipv4_list, ipv6_list, errors


def format_resolution_result(domain: str, ipv4: List[str], ipv6: List[str]) -> str:
    """Format resolution result for Telegram message."""
    msg = f"🔍 <b>{domain}</b>\n\n"
    
    if ipv4:
        msg += f"IPv4: <code>{', '.join(ipv4)}</code>\n"
    else:
        msg += "IPv4: ❌ не найдены\n"
    
    if ipv6:
        msg += f"IPv6: <code>{', '.join(ipv6)}</code>\n"
    else:
        msg += "IPv6: не найдены (опционально)\n"
    
    return msg
