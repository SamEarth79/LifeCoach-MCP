from fastapi import Depends, FastAPI, HTTPException, Response, status

from app.auth import CurrentUser, get_current_user
from app.db import check_connectivity, get_connection

app = FastAPI(title="LifeCoach API")


@app.get("/health")
async def health(response: Response) -> dict:
    is_db_reachable = await check_connectivity()
    if not is_db_reachable:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "database": "unreachable"}

    return {"status": "healthy", "database": "reachable"}


@app.get("/users/me")
async def get_my_profile(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    async with get_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id, email, display_name, created_at, updated_at
                FROM users
                WHERE id = %s
                """,
                (current_user.id,),
            )
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user_id, email, display_name, created_at, updated_at = row
    if str(user_id) != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return {
        "id": str(user_id),
        "email": email,
        "display_name": display_name,
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }
