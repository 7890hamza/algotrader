import { flushPromises, mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import { placeBrokerOrder } from '@/api/brokerClient';
import PositionToolCard from '@/components/Chart/PositionToolCard.vue';
import { resolveContractSpec } from '@/utils/chart/contractSpecs';
import { buildPositionModel, type PositionToolState } from '@/utils/chart/positionTool';

vi.mock('@/api/brokerClient', () => ({ placeBrokerOrder: vi.fn() }));

const spec = resolveContractSpec({ symbol: 'ES', minMove: 0.25 });
const state: PositionToolState = { side: 'long', time: 0, entry: 7583, stop: 7575.5, target: 7616.75, qty: 2 };

function card(lastPrice: number) {
  return mount(PositionToolCard, { props: { state, model: buildPositionModel(state, spec), spec, symbol: 'ES', lastPrice } });
}

describe('PositionToolCard: send to MT5', () => {
  it('asks first, then sends a buy limit with the stop and target', async () => {
    vi.mocked(placeBrokerOrder).mockResolvedValue({ orderId: 99, price: 7583 });
    const w = card(7590);
    expect(w.get('[data-testid=send-plan]').text()).toContain('BUY LIMIT 2 @ 7583.00');
    await w.get('[data-testid=send-plan]').trigger('click');
    expect(placeBrokerOrder).not.toHaveBeenCalled();
    expect(w.text()).toContain('to your MT5 demo?');
    await w.get('[data-testid=confirm-send]').trigger('click');
    await flushPromises();
    expect(placeBrokerOrder).toHaveBeenCalledWith({
      symbol: 'ES', orderType: 'LIMIT', tradeSide: 'BUY', volume: 2, limitPrice: 7583, stopLoss: 7575.5, takeProfit: 7616.75,
    });
    expect(w.text()).toContain('Order #99 working on MT5');
  });

  it('uses a buy stop when the entry is above the market, and shows MT5 errors', async () => {
    vi.mocked(placeBrokerOrder).mockRejectedValue(new Error('Trading is off.'));
    const w = card(7570);
    expect(w.get('[data-testid=send-plan]').text()).toContain('BUY STOP');
    await w.get('[data-testid=send-plan]').trigger('click');
    await w.get('[data-testid=confirm-send]').trigger('click');
    await flushPromises();
    expect(w.text()).toContain('Trading is off.');
  });
});
