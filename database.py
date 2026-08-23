# railway-deploy-fix

import asyncpg
import secrets
import string
from datetime import datetime


_pool = None

def generate_order_code():
    date_part = datetime.now().strftime("%Y%m%d")

    alphabet = string.ascii_uppercase + string.digits

    random_part = "".join(
        secrets.choice(alphabet)
        for _ in range(6)
    )

    return f"SOB-{date_part}-{random_part}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_id BIGINT PRIMARY KEY,
    username TEXT,
    referred_by BIGINT,
    points INTEGER NOT NULL DEFAULT 0,
    referral_rewarded BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);


CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price NUMERIC(12,2) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS vouchers (
    id BIGSERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'available',
    order_id BIGINT
);


CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    tg_id BIGINT NOT NULL REFERENCES users(tg_id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    order_code TEXT,
    status TEXT NOT NULL DEFAULT 'awaiting_utr',
    utr TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS referral_events (
    id BIGSERIAL PRIMARY KEY,
    referrer_id BIGINT NOT NULL REFERENCES users(tg_id),
    referred_id BIGINT NOT NULL REFERENCES users(tg_id),
    reward INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(referrer_id, referred_id)
);

CREATE TABLE IF NOT EXISTS reward_claims (
    id BIGSERIAL PRIMARY KEY,
    tg_id BIGINT NOT NULL REFERENCES users(tg_id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    voucher_id BIGINT NOT NULL REFERENCES vouchers(id),
    reward_name TEXT NOT NULL,
    voucher_code TEXT NOT NULL,
    points_spent INTEGER NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS idx_vouchers_product_status
ON vouchers(product_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_utr_unique
ON orders(utr)
WHERE utr IS NOT NULL;


CREATE INDEX IF NOT EXISTS idx_orders_user
ON orders(tg_id);


CREATE INDEX IF NOT EXISTS idx_orders_status
ON orders(status);
"""


async def init_db(database_url):
    global _pool

    _pool = await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=5
    )

    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA)

        await conn.execute(
            """
            ALTER TABLE orders
            ADD COLUMN IF NOT EXISTS order_code TEXT
            """
        )


async def close_db():
    global _pool

    if _pool:
        await _pool.close()
        _pool = None


# =========================
# USERS
# =========================

async def ensure_user(
    tg_id,
    username=None,
    referrer=None
):
    async with _pool.acquire() as conn:

        existing = await conn.fetchrow(
            """
            SELECT tg_id
            FROM users
            WHERE tg_id=$1
            """,
            tg_id
        )

        if existing:

            await conn.execute(
                """
                UPDATE users
                SET username=$2
                WHERE tg_id=$1
                """,
                tg_id,
                username
            )

            return False

        valid_referrer = None

        if referrer and referrer != tg_id:

            ref_exists = await conn.fetchval(
                """
                SELECT tg_id
                FROM users
                WHERE tg_id=$1
                """,
                referrer
            )

            if ref_exists:
                valid_referrer = referrer

        await conn.execute(
            """
            INSERT INTO users(
                tg_id,
                username,
                referred_by
            )
            VALUES($1,$2,$3)
            """,
            tg_id,
            username,
            valid_referrer
        )

        return True


async def get_user(tg_id):

    async with _pool.acquire() as conn:

        return await conn.fetchrow(
            """
            SELECT *
            FROM users
            WHERE tg_id=$1
            """,
            tg_id
        )


async def get_user_points(tg_id):

    async with _pool.acquire() as conn:

        result = await conn.fetchval(
            """
            SELECT points
            FROM users
            WHERE tg_id=$1
            """,
            tg_id
        )

        return result or 0

async def claim_shein_reward(tg_id):
    async with _pool.acquire() as conn:
        async with conn.transaction():

            user = await conn.fetchrow(
                """
                SELECT points
                FROM users
                WHERE tg_id=$1
                FOR UPDATE
                """,
                tg_id
            )


            if not user:
                return None

            if user["points"] < 9:
                return None

            product = await conn.fetchrow(
                """
                SELECT id, name
                FROM products
                WHERE LOWER(name) LIKE '%shein%'
                  AND active=TRUE
                LIMIT 1
                """
            )

            if not product:
                return None

            voucher = await conn.fetchrow(
                """
                SELECT id, code
                FROM vouchers
                WHERE product_id=$1
                  AND status='available'
                ORDER BY id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
                product["id"]
            )

            if not voucher:
                return None

            await conn.execute(
                """
                UPDATE vouchers
                SET status='sold'
                WHERE id=$1
                """,
                voucher["id"]
            )

            await conn.execute(
                """
                UPDATE users
                SET points=points-9
                WHERE tg_id=$1
                """,
                tg_id
            )

            await conn.execute(
                """
                INSERT INTO reward_claims (
                    tg_id,
                    product_id,
                    voucher_id,
                    reward_name,
                    voucher_code,
                    points_spent
                )
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                tg_id,
                product["id"],
                voucher["id"],
                product["name"],
                voucher["code"],
                9
            )

            return {
                "reward_name": product["name"],
                "voucher_code": voucher["code"],
                "points_spent": 9
            }

async def get_reward_claims(tg_id):
    async with _pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT
                reward_name,
                voucher_code,
                points_spent,
                claimed_at
            FROM reward_claims
            WHERE tg_id=$1
            ORDER BY claimed_at DESC
            LIMIT 20
            """,
            tg_id
        )


# =========================
# SETTINGS
# =========================

async def set_setting(key, value):

    async with _pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO settings(key,value)
            VALUES($1,$2)

            ON CONFLICT(key)
            DO UPDATE SET value=EXCLUDED.value
            """,
            key,
            str(value)
        )


async def get_setting(key, default=""):

    async with _pool.acquire() as conn:

        value = await conn.fetchval(
            """
            SELECT value
            FROM settings
            WHERE key=$1
            """,
            key
        )

        return value if value is not None else default


# =========================
# PRODUCTS
# =========================

async def add_product(
    name,
    description,
    price
):

    async with _pool.acquire() as conn:

        return await conn.fetchval(
            """
            INSERT INTO products(
                name,
                description,
                price
            )
            VALUES($1,$2,$3)

            RETURNING id
            """,
            name,
            description,
            price
        )


async def get_products():

    async with _pool.acquire() as conn:

        return await conn.fetch(
            """
            SELECT
                p.*,
                COUNT(v.id)
                FILTER(
                    WHERE v.status='available'
                ) AS stock

            FROM products p

            LEFT JOIN vouchers v
            ON v.product_id=p.id

            GROUP BY p.id

            ORDER BY p.id
            """
        )


async def get_active_products():

    async with _pool.acquire() as conn:

        return await conn.fetch(
            """
            SELECT
                p.*,
                COUNT(v.id)
                FILTER(
                    WHERE v.status='available'
                ) AS stock

            FROM products p

            LEFT JOIN vouchers v
            ON v.product_id=p.id

            WHERE p.active=TRUE

            GROUP BY p.id

            ORDER BY p.id
            """
        )


async def get_product(product_id):

    async with _pool.acquire() as conn:

        return await conn.fetchrow(
            """
            SELECT *
            FROM products
            WHERE id=$1
            """,
            product_id
        )


async def update_product_price(
    product_id,
    new_price
):

    async with _pool.acquire() as conn:

        result = await conn.execute(
            """
            UPDATE products
            SET price=$1
            WHERE id=$2
            """,
            new_price,
            product_id
        )

        return result == "UPDATE 1"


async def update_product_name(
    product_id,
    name
):

    async with _pool.acquire() as conn:

        result = await conn.execute(
            """
            UPDATE products
            SET name=$1
            WHERE id=$2
            """,
            name,
            product_id
        )

        return result == "UPDATE 1"


async def update_product_description(
    product_id,
    description
):

    async with _pool.acquire() as conn:

        result = await conn.execute(
            """
            UPDATE products
            SET description=$1
            WHERE id=$2
            """,
            description,
            product_id
        )

        return result == "UPDATE 1"


async def set_product_status(
    product_id,
    active
):

    async with _pool.acquire() as conn:

        result = await conn.execute(
            """
            UPDATE products
            SET active=$1
            WHERE id=$2
            """,
            active,
            product_id
        )

        return result == "UPDATE 1"


# =========================
# VOUCHERS / STOCK
# =========================

async def add_vouchers(
    product_id,
    codes
):

    added = 0

    async with _pool.acquire() as conn:

        for code in codes:

            code = code.strip()

            if not code:
                continue

            result = await conn.execute(
                """
                INSERT INTO vouchers(
                    product_id,
                    code
                )
                VALUES($1,$2)

                ON CONFLICT(code)
                DO NOTHING
                """,
                product_id,
                code
            )

            if result == "INSERT 0 1":
                added += 1

    return added


async def stock_count(product_id):

    async with _pool.acquire() as conn:

        return await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM vouchers
            WHERE product_id=$1
            AND status='available'
            """,
            product_id
        )


async def get_stock(product_id):

    return await stock_count(product_id)


# =========================
# ORDERS
# =========================

async def create_order(
    tg_id,
    product_id,
    qty
):

    async with _pool.acquire() as conn:

        async with conn.transaction():

            product = await conn.fetchrow(
                """
                SELECT *
                FROM products
                WHERE id=$1
                AND active=TRUE
                FOR UPDATE
                """,
                product_id
            )

            if not product:
                raise ValueError(
                    "Product is unavailable."
                )

            available = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM vouchers

                WHERE product_id=$1
                AND status='available'
                """,
                product_id
            )

            if available < qty:
                raise ValueError(
                    "Not enough voucher stock."
                )

            amount = product["price"] * qty

            order_code = generate_order_code()

            order_id = await conn.fetchval(
                """
                INSERT INTO orders(
                    tg_id,
                    product_id,
                    qty,
                    amount,
                    order_code
                )

                VALUES($1,$2,$3,$4,$5)

                RETURNING id
                """,
                tg_id,
                product_id,
                qty,
                amount,
                order_code
            )

            return order_id, amount, product["name"]

async def set_utr(
    order_id,
    tg_id,
    utr
):

    utr = utr.strip()

    if not utr:
        return False
        
    if not utr.isdigit():
        return False

    async with _pool.acquire() as conn:

        try:

            result = await conn.execute(
                """
                UPDATE orders

                SET
                    utr=$1,
                    status='pending_verification'

                WHERE id=$2
                AND tg_id=$3
                AND status='awaiting_utr'
                """,
                utr,
                order_id,
                tg_id
            )

            return result == "UPDATE 1"

        except asyncpg.UniqueViolationError:

            return False


async def get_order(order_id):

    async with _pool.acquire() as conn:

        return await conn.fetchrow(
            """
            SELECT
                o.*,
                p.name AS product_name

            FROM orders o

            JOIN products p
            ON p.id=o.product_id

            WHERE o.id=$1
            """,
            order_id
        )


async def get_user_orders(tg_id):

    async with _pool.acquire() as conn:

        return await conn.fetch(
            """
            SELECT
                o.*,
                p.name AS product_name

            FROM orders o

            JOIN products p
            ON p.id=o.product_id

            WHERE o.tg_id=$1

            ORDER BY o.id DESC

            LIMIT 30
            """,
            tg_id
        )


async def get_pending_orders():

    async with _pool.acquire() as conn:

        return await conn.fetch(
            """
            SELECT
                o.*,
                p.name AS product_name,
                u.username

            FROM orders o

            JOIN products p
            ON p.id=o.product_id

            JOIN users u
            ON u.tg_id=o.tg_id

            WHERE o.status='pending_verification'

            ORDER BY o.created_at ASC

            LIMIT 50
            """
        )


# =========================
# APPROVE / REJECT
# =========================

async def approve_order(
    order_id,
    referral_reward=1
):

            async with _pool.acquire() as conn:

            async with conn.transaction():

                order = await conn.fetchrow(
                    """
                    SELECT *
                    FROM orders

                    WHERE id=$1

                    FOR UPDATE
                    """,
                    order_id
                )

                if not order:
                    return None, []

                if order["status"] != "pending_verification":
                    return None, []
                    
                product = await conn.fetchrow(
                    """
                    SELECT name
                    FROM products
                    WHERE id=$1
                    """,
                    order["product_id"]
                )

        is_shein = (
            product
            and "shein" in product["name"].lower()
        )

        if not is_shein:
            referral_reward = 0

            vouchers = await conn.fetch(
                """
                SELECT
                    id,
                    code

                FROM vouchers

                WHERE product_id=$1
                AND status='available'

                ORDER BY id

                LIMIT $2

                FOR UPDATE
                """,
                order["product_id"],
                order["qty"]
            )

            if len(vouchers) < order["qty"]:
                raise ValueError(
                    "Not enough voucher stock."
                )

            voucher_ids = [
                row["id"]
                for row in vouchers
            ]

            await conn.execute(
                """
                UPDATE vouchers

                SET
                    status='sold',
                    order_id=$1

                WHERE id=ANY($2::bigint[])
                """,
                order_id,
                voucher_ids
            )

            await conn.execute(
                """
                UPDATE orders

                SET status='approved'

                WHERE id=$1
                """,
                order_id
            )

            # +1 referral point on first
            # successful purchase only

            user = await conn.fetchrow(
                """
                SELECT
                    referred_by,
                    referral_rewarded

                FROM users

                WHERE tg_id=$1
                """,
                order["tg_id"]
            )

            if (
                user
                and user["referred_by"]
                and not user["referral_rewarded"]
                and referral_reward > 0
            ):

                referrer_id = user["referred_by"]

                await conn.execute(
                    """
                    UPDATE users

                    SET points=points+$1

                    WHERE tg_id=$2
                    """,
                    referral_reward,
                    referrer_id
                )

                await conn.execute(
                    """
                    UPDATE users

                    SET referral_rewarded=TRUE

                    WHERE tg_id=$1
                    """,
                    order["tg_id"]
                )

                await conn.execute(
                    """
                    INSERT INTO referral_events(
                        referrer_id,
                        referred_id,
                        reward
                    )

                    VALUES($1,$2,$3)

                    ON CONFLICT DO NOTHING
                    """,
                    referrer_id,
                    order["tg_id"],
                    referral_reward
                )

            return (
                order,
                [
                    row["code"]
                    for row in vouchers
                ]
            )


async def reject_order(order_id):

    async with _pool.acquire() as conn:

        result = await conn.execute(
            """
            UPDATE orders

            SET status='rejected'

            WHERE id=$1

            AND status='pending_verification'
            """,
            order_id
        )

        return result == "UPDATE 1"


# =========================
# VOUCHER RECOVERY
# =========================

async def get_order_codes(
    order_id,
    tg_id
):

    async with _pool.acquire() as conn:

        order = await conn.fetchrow(
            """
            SELECT *

            FROM orders

            WHERE id=$1
            AND tg_id=$2
            """,
            order_id,
            tg_id
        )

        if not order:
            return None

        if order["status"] != "approved":
            return None

        rows = await conn.fetch(
            """
            SELECT code

            FROM vouchers

            WHERE order_id=$1

            ORDER BY id
            """,
            order_id
        )

        return [
            row["code"]
            for row in rows
        ]

async def get_order_codes_by_code(
    order_code,
    tg_id
):

    async with _pool.acquire() as conn:

        order = await conn.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE order_code=$1
            AND tg_id=$2
            """,
            order_code,
            tg_id
        )

        if not order:
            return None

        if order["status"] != "approved":
            return None

        rows = await conn.fetch(
            """
            SELECT code
            FROM vouchers
            WHERE order_id=$1
            ORDER BY id
            """,
            order["id"]
        )

        return [
            row["code"]
            for row in rows
        ]
        
# =========================
# REFERRALS
# =========================

async def get_referral_count(tg_id):

    async with _pool.acquire() as conn:

        return await conn.fetchval(
            """
            SELECT COUNT(*)

            FROM referral_events

            WHERE referrer_id=$1
            """,
            tg_id
        )


async def get_referral_points(tg_id):

    return await get_user_points(tg_id)

# =========================
# BOT COMPATIBILITY HELPERS
# =========================

async def user_points(tg_id):
    return await get_user_points(tg_id)


async def user_orders(tg_id):
    return await get_user_orders(tg_id)


async def pending_orders():
    return await get_pending_orders()


async def order_codes(order_code, tg_id):
    return await get_order_codes_by_code(
        order_code,
        tg_id
    )
