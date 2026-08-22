# Production snapshot: BeauQuot 3.1.4 fixed2

This repository documentation records the production package used for the 3.1.4 deployment.

## Source package

Archive: `quote-bot-v3.1.4-fixed2.tar.gz`

SHA-256 of `main.py` in the supplied production archive:

`d39648634904fd8ab263223e3e443d24a5300e2b07056e93383fb0083bc42282`

Git blob SHA of that `main.py` content:

`db1613a9eeef6cfdcabacbe86d28c1576c56e894`

The archive contains:

- `main.py`
- `requirements.txt`
- `UPDATE_NOTES.md`
- `UPDATE_NOTES_3_1_4.md`
- `VISUAL_ENGINE_3_1_2.md`
- `VISUAL_ENGINE_3_1_3.md`
- `VISUAL_ENGINE_3_1_4.md`
- `TEST_3_1_4.sh`

It does not contain `.env`, SQLite production state, or service secrets.

## Important

The production archive is the authoritative runtime snapshot for the 3.1.4 deployment. Repository documentation is synchronized to its 3.1.4 semantic-art-direction contract without copying secrets or generated state.
