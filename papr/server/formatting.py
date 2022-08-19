def format_formal_review(reviews):
    txt = "--- BEGINNING OF REVIEW ---"

    for ind, review in enumerate(reviews):
        txt += "*** REVIEWER {ind+1} ***\n\n"
        txt += review
        txt += "\n\n\n"

    txt += "--- END OF REVIEW ---"
    return txt
