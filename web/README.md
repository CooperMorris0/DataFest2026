# Flood map web demo

A small Express server for the hackathon demo. It serves the Oakland flood
vulnerability map and adds a community layer where neighbors can post help
requests and volunteer.

Login is a **demo login**: you just type a display name. There is no real
authentication (no passwords), by design. Data is kept in `data/db.json`.

## Run

```
npm install
npm start
```

Open http://localhost:3000 (set `PORT` to change the port). Run tests with `npm test`.

## API

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/api/login` | `{name}` → `{user}`, sets the `fw_user` cookie |
| POST | `/api/logout` | clears the cookie |
| GET | `/api/me` | `{user}` or `{user: null}` |
| GET | `/api/requests` | `{requests}`, newest first, all statuses |
| POST | `/api/requests` | login required; `{lat, lng, category, details, people}` → 201 `{request}` |
| POST | `/api/requests/:id/volunteer` | login required; sets status to `help_on_the_way` |
| POST | `/api/requests/:id/resolve` | requester only; sets status to `resolved` |

Categories: flooding, sandbags, evacuation, cleanup, supplies, other.
Locations must be inside Oakland (lat 37.69–37.89, lng -122.36 to -122.11).
