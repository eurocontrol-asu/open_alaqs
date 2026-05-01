class Singleton(type):
    """
    Define a class as Singleton using it as a metaclass:

        class MyStore(SomeBase, metaclass=Singleton): ...

    All Singleton subclasses register themselves so they can all be
    invalidated at once with ``Singleton.reset_all()``.  This is required
    when the user opens a different .alaqs database in the same QGIS Python
    session — without a reset every Store silently serves cached data from
    the previous file.

    Classes that should survive a reset (e.g. module registries populated at
    import time) must set the class attribute ``_singleton_persistent = True``.
    ``reset_all()`` skips those classes.
    """

    _registry: set = set()

    def __init__(cls, name, bases, dict):
        super(Singleton, cls).__init__(name, bases, dict)
        cls.instance = None
        Singleton._registry.add(cls)

    def __call__(cls, *args, **kw):
        if cls.instance is None:
            cls.instance = super(Singleton, cls).__call__(*args, **kw)
        return cls.instance

    def reset(cls) -> None:
        """Destroy the cached instance so the next call re-initialises it."""
        cls.instance = None

    @staticmethod
    def reset_all() -> None:
        """
        Invalidate every non-persistent Singleton store.

        Call at the start of EmissionCalculation.__init__ (or in the QGIS
        dialog openProject handler) whenever a new database file is opened,
        so all stores reload from the new file rather than serving stale data.

        Classes with ``_singleton_persistent = True`` (e.g. ModuleRegistry
        subclasses, which are populated once at import time) are skipped.

        Usage::

            from open_alaqs.core.tools.Singleton import Singleton
            Singleton.reset_all()
        """
        for cls in Singleton._registry:
            if not getattr(cls, "_singleton_persistent", False):
                cls.instance = None
