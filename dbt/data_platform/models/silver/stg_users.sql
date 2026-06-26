-- Silver: cleaned & conformed users (typed, lower-cased email, renamed keys).
with src as (
    select * from {{ source('bronze', 'users') }}
)

select
    cast(id as integer)       as user_id,
    name                      as full_name,
    username,
    lower(email)              as email,
    nullif(phone, '')         as phone,
    nullif(website, '')       as website,
    company_name,
    city,
    zipcode,
    cast(lat as double)       as latitude,
    cast(lng as double)       as longitude
from src
