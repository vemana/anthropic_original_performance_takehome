import heapq

class InsertionOrderedSet:
    def __init__(self):
        self.s = set()
        self.l = []


    def add(self, x):
        if x in self.s:
            return False
        self.s.add(x)
        self.l.append(x)
        return True


    def __lt__(self, that):
        raise ValueError("HERE")

    def __iter__(self):
        for item in self.l:
            yield item

    
    def __str__(self):
        ret = "{"
        for item in self:
            ret += str(item)
            ret += ', '
        ret += '}'
        return ret


    @classmethod
    def initial(cls, *elements):
        ios = cls()
        for item in elements:
            ios.add(item)
        return ios


from sortedcontainers import SortedSet
class MinHeap:
    def __init__(self):
        self.array = SortedSet([])
#         self.array = []

    def __iter__(self):
        for x in self.array:
            yield x


    def __len__(self):
        return len(self.array)


    def add(self, item):
        self.append(item)


    def append(self, item):
        return self.array.add(item)
#         return self.array.append(item)


    def extend(self, arr):
        for item in arr:
            self.add(item)


    def remove(self, item):
        try:
            self.array.remove(item)
        except ValueError as ex:
            print(f"When failed, len = {len(self)}\n{item}\n\n")
            for x in self.array:
                print(x)
            raise ex


class TestMinHeap:
    def __init__(self):
        a = MinHeap()
        assert len(a) == 0
        a.append(1)
        assert len(a) == 1
        a.append(-1)
        assert len(a) == 2
        a.append(3)
        assert len(a) == 3
        a.remove(1)
        assert(len(a) == 2)
        arr = [x for x in a]
        assert arr == [-1, 3]
