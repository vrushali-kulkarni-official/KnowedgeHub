Perfect. Before learning **JWT**, **OAuth**, etc., you need to understand one of FastAPI's superpowers: **automatic parameter validation**.

Let's build this concept from the ground up.

---

# Step 1: What is a Parameter?

A parameter is simply **data that the client sends to your API**.

For example:

```
GET /items/?q=laptop
```

The client is sending

```
q = "laptop"
```

Similarly,

```
GET /items/25
```

The client is sending

```
item_id = 25
```

These values are called **request parameters**.

---

# Step 2: The Problem Without Validation

Imagine you write this:

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/items/")
def read_items(q: str):
    return {"q": q}
```

A client sends

```
/items/?q=abc
```

Works perfectly.

Now suppose they send

```
/items/?q=a
```

Maybe your application requires at least 3 characters.

Nothing stops them.

Now suppose they send

```
/items/?q=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

Still accepted.

Now suppose they send

```
/items/?q=@#$%^&*
```

Still accepted.

Your code now has to manually check everything.

Example:

```python
@app.get("/items/")
def read_items(q: str):

    if len(q) < 3:
        return {"error": "Too short"}

    if len(q) > 50:
        return {"error": "Too long"}

    if q != "fixedquery":
        return {"error": "Invalid"}

    return {"q": q}
```

Imagine doing this for hundreds of APIs.

That becomes ugly.

---

# Step 3: FastAPI Solves This

Instead of validating yourself...

you simply describe the rules.

```python
Query(min_length=3, max_length=50, pattern="^fixedquery$")
```

FastAPI automatically checks everything **before your function runs.**

Think of it like this:

```
Incoming Request
        │
        ▼
FastAPI Validation
        │
        ▼
Is data valid?
      │
 ┌────┴─────┐
 │          │
Yes         No
 │          │
 ▼          ▼
Call        Return 422 Error
Function
```

Notice:

Your function isn't even called if validation fails.

---

# Step 4: Understanding Query()

Let's look at

```python
Query(...)
```

Many beginners think Query stores data.

It doesn't.

It simply tells FastAPI

> "This value comes from the URL query string, and here are the rules."

Example

```python
q: str | None = Query(default=None)
```

means

```
Parameter name : q

Location :
Query String

Default :
None

Type :
str or None
```

---

# Step 5: Query Parameters

Suppose your URL is

```
/items/?q=laptop
```

Everything after

```
?
```

is called the query string.

```
/items/?q=laptop&page=3&sort=price
```

contains

```
q = laptop

page = 3

sort = price
```

These are Query Parameters.

FastAPI knows this because you wrote

```python
Query(...)
```

---

# Step 6: min_length

Suppose

```python
q: str = Query(min_length=3)
```

Valid

```
?q=cat
```

```
Length = 3
```

Accepted.

---

Valid

```
?q=laptop
```

Length = 6

Accepted.

---

Invalid

```
?q=hi
```

Length = 2

Rejected.

FastAPI automatically returns

```json
{
  "detail": [
    {
      "msg": "String should have at least 3 characters"
    }
  ]
}
```

Your function never executes.

---

# Step 7: max_length

Suppose

```python
Query(max_length=5)
```

Allowed

```
apple
```

Rejected

```
pineapple
```

Again,

FastAPI stops the request before your code runs.

---

# Step 8: pattern (Regex)

This is the most confusing part for beginners.

Your code

```python
pattern = "^fixedquery$"
```

is a Regular Expression.

Let's simplify.

Suppose

```
pattern="cat"
```

means

Contains "cat"

Examples

```
cat
```

Accepted.

```
mycat
```

Accepted.

```
cat123
```

Accepted.

---

Now look at yours

```
^fixedquery$
```

Let's decode it.

```
^
```

means

Start of string

```
$
```

means

End of string

So

```
^fixedquery$
```

means

```
Start

fixedquery

End
```

Nothing before.

Nothing after.

Only

```
fixedquery
```

is allowed.

Accepted

```
fixedquery
```

Rejected

```
fixedquery123
```

Rejected

```
abcfixedquery
```

Rejected

```
myfixedquery
```

Rejected

Only exactly

```
fixedquery
```

works.

---

# Step 9: description

```python
description = "Search query string"
```

This does **NOT** affect validation.

It is used in Swagger UI.

When you open

```
/docs
```

FastAPI shows

```
q

Search query string
```

Very useful documentation.

---

# Step 10: Path()

Now let's move to

```python
Path(...)
```

Your API

```python
/items/{item_id}
```

means

```
/items/50
```

Here

```
50
```

is a Path Parameter.

FastAPI gets it using

```python
item_id: int = Path(...)
```

---

# Step 11: ge

```python
ge = 1
```

means

Greater Than or Equal To

```
1
```

Allowed

```
50
```

Allowed

```
100
```

Allowed

```
0
```

Rejected

```
-5
```

Rejected

---

# Step 12: le

```
le = 1000
```

means

Less Than or Equal To

Allowed

```
1000
```

Allowed

```
500
```

Allowed

Rejected

```
2000
```

---

Together

```python
Path(ge=1, le=1000)
```

means

```
1 ≤ item_id ≤ 1000
```

---

# Step 13: title

```python
title = "The ID of the item"
```

Again,

This is documentation only.

Swagger displays it.

No validation.

---

# Step 14: Multiple Query Parameters

This one surprises many people.

You wrote

```python
tags: list[str] = Query(default=[])
```

Notice

```
list[str]
```

FastAPI understands

The client may send multiple values.

Example URL

```
/numbers/?tags=python&tags=fastapi&tags=jwt
```

FastAPI automatically converts this into

```python
["python", "fastapi", "jwt"]
```

Your function receives

```python
tags = ["python", "fastapi", "jwt"]
```

without writing any parsing code.

---

# Step 15: Why Query(default=[])? Why Not Just []?

Without Query

```python
tags: list[str] = []
```

FastAPI would think

```
Body parameter
```

instead of

```
Query parameter
```

By writing

```python
Query(default=[])
```

you're telling FastAPI

> "This list comes from the URL query string."

---

# Step 16: What Happens Internally?

Imagine the request

```
GET /items/?q=hi
```

Execution flow:

```
Client
   │
   ▼
FastAPI receives request
   │
   ▼
Extract q
   │
   ▼
Check type

Is it string?
   │
   ▼
Check min_length

Length >= 3 ?
   │
   ▼
NO
   │
   ▼
Return HTTP 422
```

Your function

```python
read_items()
```

is **never called**.

---

# Step 17: Summary Table

| Function      | Used For                         | Example                           |
| ------------- | -------------------------------- | --------------------------------- |
| `Query()`     | Query parameters (`?q=test`)     | Search, filters, pagination       |
| `Path()`      | URL path parameters (`/items/5`) | Resource IDs                      |
| `min_length`  | Minimum string length            | `"abc"`                           |
| `max_length`  | Maximum string length            | `"abcdef"` rejected if limit is 5 |
| `pattern`     | Regex validation                 | Email, usernames, exact strings   |
| `ge`          | Greater than or equal            | `>= 1`                            |
| `gt`          | Greater than                     | `> 1`                             |
| `le`          | Less than or equal               | `<= 100`                          |
| `lt`          | Less than                        | `< 100`                           |
| `description` | API documentation only           | Shows in `/docs`                  |
| `title`       | API documentation only           | Shows in `/docs`                  |

## The big idea

FastAPI parameter validation follows a simple pattern:

1. **You declare** what you expect (type, location, and validation rules).
2. **FastAPI extracts** the value from the request (query, path, etc.).
3. **FastAPI validates** the value automatically.
4. If validation **passes**, your endpoint function is called with properly typed values.
5. If validation **fails**, FastAPI returns a **422 Unprocessable Entity** response describing the validation errors, and your function is not executed.

This declarative approach is one of the reasons FastAPI code stays clean: you describe *what* is valid, and FastAPI handles *how* to enforce it.
