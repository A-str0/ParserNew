def format_url(url: str, start: str) -> str:
    if not url.startswith("http"):
        return f"{start}{url}"
    
    return url

def format_email_subject(unformatted: str, **kwargs) -> str:
    try:
        # Count placeholders in the string
        placeholder_count = unformatted.count("{}")
        provided_args = len(kwargs)

        if placeholder_count != provided_args:
            raise Exception(f"Mismatch in placeholder count ({placeholder_count}) and provided arguments ({provided_args})")
        
        # Format the string with provided kwargs
        formatted_subject = unformatted.format(*[kwargs[key] for key in sorted(kwargs.keys())])
        return formatted_subject
    
    except Exception as e:
        raise Exception(f"Error formatting email subject: {e}")