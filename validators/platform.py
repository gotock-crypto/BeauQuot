def validate_post_payload(text, image, max_len):
    if not image: return False,'image is empty'
    if not text or not text.strip(): return False,'text is empty'
    if len(text)>max_len: return False,f'text exceeds {max_len}'
    return True,''