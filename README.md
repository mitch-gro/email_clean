Installation steps
1. Run `cp .env.example .env`.
2. Create a [GitHub access token](https://github.com/settings/tokens). Update `.env.example` with the value.
3. Create a [Gmail access token](https://github.com/settings/tokens). Save it as `credentials.json` in the directory root.
4. Fill out your Github username in `.env`
5. Install everything with `make install`

If you don't have poetry installed, follow this link: https://python-poetry.org/

Running the code
`make run`