**`@tool(parse_docstring=True)`** is a decorator from **LangChain** (specifically `langchain_core.tools`). It turns a normal Python function into a **Tool** that an LLM agent can call.

### What it does in simple terms

When you put this decorator on a function:

```python
from langchain_core.tools import tool

@tool(parse_docstring=True)
def search_web(query: str, max_results: int = 5) -> str:
    """Search the web for information.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.
    """
    # your code here
    return "some results"
```

LangChain does two important things:

1. **Creates a Tool object** that agents can use.
2. **Automatically reads the docstring** (the `"""..."""` text) and extracts:
   - The overall description of the tool
   - The description of every parameter

This information is then put into a structured schema (usually a Pydantic model) that the LLM can understand.

### Why `parse_docstring=True` matters

By default, `@tool` only looks at:
- The function name
- The type hints (`str`, `int`, etc.)
- The return type

It **ignores** the human-readable descriptions written in the docstring.

When you set `parse_docstring=True`, LangChain **parses the docstring** (it expects **Google-style** docstrings) and adds the descriptions to the tool’s schema.

**Without it** the LLM only sees something like:
> Tool name: `search_web`  
> Parameters: `query` (string), `max_results` (integer)

**With it** the LLM sees:
> Tool name: `search_web`  
> Description: Search the web for information.  
> Parameters:  
> - `query`: The search query string.  
> - `max_results`: Maximum number of results to return.

Better descriptions → the LLM makes better decisions about when and how to call the tool.

### Step-by-step what happens under the hood

1. You write a normal Python function with type hints and a Google-style docstring.
2. You decorate it with `@tool(parse_docstring=True)`.
3. LangChain inspects the function signature (name, parameters, types, defaults).
4. It parses the docstring looking for:
   - The first paragraph → becomes the tool’s main description
   - The `Args:` section → becomes the description for each parameter
5. It builds a Pydantic model (the `args_schema`) that contains both the types **and** the descriptions.
6. It wraps everything into a `StructuredTool` (or similar) object that agents can use.

### Important notes about the docstring style

LangChain’s docstring parser expects **Google style**, like this:

```python
"""Short one-line description.

Longer description if needed.

Args:
    param1: Description of param1.
    param2: Description of param2.
"""
```

Other styles (NumPy, Sphinx, etc.) may not be parsed correctly unless the library supports them.

### Common options you can combine

```python
@tool(
    "custom_name",              # Optional: override the tool name
    parse_docstring=True,       # Parse the docstring
    return_direct=True,         # Optional: return the result directly to the user
)
```

### Quick comparison

| Approach                        | Parameter descriptions come from | Extra code needed? |
|--------------------------------|----------------------------------|--------------------|
| `@tool` (default)              | None                             | No                 |
| `@tool(parse_docstring=True)`  | Docstring                       | No                 |
| `@tool(args_schema=MyModel)`   | Pydantic `Field(description=...)`| Yes                |

### Summary

`@tool(parse_docstring=True)` is the convenient way to turn a well-documented Python function into an LLM-ready tool **without** writing a separate Pydantic schema. It reads the descriptions you already wrote in the docstring and automatically includes them so the language model understands what each argument means.






**`@tool(parse_docstring=True)`** is a decorator from **LangChain** (specifically `langchain_core.tools`). It turns a normal Python function into a **Tool** that an LLM agent can call.

### What it does in simple terms

When you put this decorator on a function:

```python
from langchain_core.tools import tool

@tool(parse_docstring=True)
def search_web(query: str, max_results: int = 5) -> str:
    """Search the web for information.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.
    """
    # your code here
    return "some results"
```

LangChain does two important things:

1. **Creates a Tool object** that agents can use.
2. **Automatically reads the docstring** (the `"""..."""` text) and extracts:
   - The overall description of the tool
   - The description of every parameter

This information is then put into a structured schema (usually a Pydantic model) that the LLM can understand.

### Why `parse_docstring=True` matters

By default, `@tool` only looks at:
- The function name
- The type hints (`str`, `int`, etc.)
- The return type

It **ignores** the human-readable descriptions written in the docstring.

When you set `parse_docstring=True`, LangChain **parses the docstring** (it expects **Google-style** docstrings) and adds the descriptions to the tool’s schema.

**Without it** the LLM only sees something like:
> Tool name: `search_web`  
> Parameters: `query` (string), `max_results` (integer)

**With it** the LLM sees:
> Tool name: `search_web`  
> Description: Search the web for information.  
> Parameters:  
> - `query`: The search query string.  
> - `max_results`: Maximum number of results to return.

Better descriptions → the LLM makes better decisions about when and how to call the tool.

### Step-by-step what happens under the hood

1. You write a normal Python function with type hints and a Google-style docstring.
2. You decorate it with `@tool(parse_docstring=True)`.
3. LangChain inspects the function signature (name, parameters, types, defaults).
4. It parses the docstring looking for:
   - The first paragraph → becomes the tool’s main description
   - The `Args:` section → becomes the description for each parameter
5. It builds a Pydantic model (the `args_schema`) that contains both the types **and** the descriptions.
6. It wraps everything into a `StructuredTool` (or similar) object that agents can use.

### Important notes about the docstring style

LangChain’s docstring parser expects **Google style**, like this:

```python
"""Short one-line description.

Longer description if needed.

Args:
    param1: Description of param1.
    param2: Description of param2.
"""
```

Other styles (NumPy, Sphinx, etc.) may not be parsed correctly unless the library supports them.

### Common options you can combine

```python
@tool(
    "custom_name",              # Optional: override the tool name
    parse_docstring=True,       # Parse the docstring
    return_direct=True,         # Optional: return the result directly to the user
)
```

### Quick comparison

| Approach                        | Parameter descriptions come from | Extra code needed? |
|--------------------------------|----------------------------------|--------------------|
| `@tool` (default)              | None                             | No                 |
| `@tool(parse_docstring=True)`  | Docstring                       | No                 |
| `@tool(args_schema=MyModel)`   | Pydantic `Field(description=...)`| Yes                |

### Summary

`@tool(parse_docstring=True)` is the convenient way to turn a well-documented Python function into an LLM-ready tool **without** writing a separate Pydantic schema. It reads the descriptions you already wrote in the docstring and automatically includes them so the language model understands what each argument means.
