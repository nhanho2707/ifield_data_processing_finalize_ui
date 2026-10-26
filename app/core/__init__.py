import collections
import collections.abc

# savReaderWriter (and hyper) still import these names from `collections`,
# which were removed in Python 3.10. Alias them before anything imports those libraries.
collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping
collections.MutableSet = collections.abc.MutableSet
collections.MutableMapping = collections.abc.MutableMapping
