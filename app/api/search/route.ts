import { NextResponse } from 'next/server';

const isDescriptionMatch = (transactionDescription: string, description: string): boolean => {
  return transactionDescription
    .replace(/\s+/g, '')
    .toLowerCase()
    .includes(description.replace(/\s+/g, '').toLowerCase());
};

const isCategoryMatch = (categoryInfo, parentCategoryInfo, parentCategory) => {
  if (!parentCategory || parentCategory.length === 0) {
    return false;
  }
  return parentCategory.some(
    (cat) =>
      (parentCategoryInfo && parentCategoryInfo.id === cat) ||
      (categoryInfo && categoryInfo.id === cat)
  );
};

const isAmountMatch = (transaction, minAmount, maxAmount) => {
  const amountValue = parseFloat(transaction?.attributes?.amount?.value);
  if (isNaN(amountValue)) {
    return true;
  }
  return !(
    (minAmount !== undefined && amountValue < minAmount) ||
    (maxAmount !== undefined && amountValue > maxAmount)
  );
};

const fetchTransactionsFromUPBank = async (
  startDate: string,
  endDate: string,
  account: string,
  description?: string,
  category?: string,
  minAmount?: number,
  maxAmount?: number
) => {
  const ACCESS_TOKEN = process.env.UP_API_TOKEN;
  const ACCOUNT_IDS = {
    IC_INDIVIDUAL: process.env.IC_INDIVIDUAL || '',
    TWO_UP: process.env.TWO_UP || '',
    BILLS: process.env.BILLS || '',
    GIFTS: process.env.GIFTS || '',
    KIDS: process.env.KIDS || '',
    EXTRAS: process.env.EXTRAS || '',
    HOLIDAYS: process.env.HOLIDAYS || '',
    SUPER: process.env.SUPER || '',
    INVESTMENTS: process.env.INVESTMENTS || '',
    RAINY_DAY: process.env.RAINY_DAY || '',
    EMERGENCY: process.env.EMERGENCY || '',
    HOME_DEPOSIT: process.env.HOME_DEPOSIT || '',
    TRANSPORT: process.env.TRANSPORT || '',
    HEALTH: process.env.HEALTH || '',
    GROCERIES: process.env.GROCERIES || '',
    PERSONAL_SAVER: process.env.PERSONAL_SAVER || '',
    RENT: process.env.RENT || '',
  };

  let accountIdsToFetch = [];

  if (account === 'ALL') {
    accountIdsToFetch = Object.values(ACCOUNT_IDS);
  } else {
    accountIdsToFetch = [ACCOUNT_IDS[account] || ''];
  }

  if (accountIdsToFetch.includes('')) {
    return { error: 'Invalid account selected' };
  }

  const headers = {
    Authorization: `Bearer ${ACCESS_TOKEN}`,
    'Content-Type': 'application/json',
  };

  const params = new URLSearchParams({
    ...(startDate && { 'filter[since]': `${startDate}T00:00:00Z` }),
    ...(endDate && { 'filter[until]': `${endDate}T23:59:59Z` }),
    'page[size]': '100',
  });

  const fetchTransactionsForAccount = async (accountId: string) => {
    const url = `https://api.up.com.au/api/v1/accounts/${accountId}/transactions?${params.toString()}`;

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers,
      });

      if (response.ok) {
        const data = await response.json();

        if (data && Array.isArray(data.data)) {
          // Filter transactions by description, category, and amount if provided
          return data.data
            .filter((transaction) => {
              const categoryInfo =
                transaction.relationships?.category?.data || null;
              const parentCategoryInfo =
                transaction.relationships?.parentCategory?.data || null;

              return (
                (!description ||
                  isDescriptionMatch(
                    transaction.attributes.description,
                    description
                  )) &&
                (!category ||
                  isCategoryMatch(
                    categoryInfo,
                    parentCategoryInfo,
                    category.split(',')
                  )) &&
                isAmountMatch(transaction, minAmount, maxAmount)
              );
            })
            .map((transaction: any) => ({
              id: transaction.id,
              attributes: {
                description: transaction.attributes.description,
                amount: {
                  currencyCode: transaction.attributes.amount.currencyCode,
                  value: transaction.attributes.amount.value,
                  valueInBaseUnits:
                    transaction.attributes.amount.valueInBaseUnits,
                },
                settledAt: transaction.attributes.settledAt,
                category: transaction.attributes.category,
                account: transaction.attributes.account,
              },
              relationships: {
                category: {
                  data: {
                    id:
                      transaction.relationships.category?.data?.id || 'Unknown',
                  },
                },
              },
            }));
        } else {
          throw new Error('Invalid data structure');
        }
      } else {
        console.error('Error fetching data:', await response.json());
        throw new Error('Failed to retrieve data');
      }
    } catch (error) {
      console.error('Error in GET request:', error);
      throw new Error('Failed to process the request');
    }
  };

  try {
    const allTransactions = await Promise.all(
      accountIdsToFetch.map(accountId => fetchTransactionsForAccount(accountId))
    );

    const allData = allTransactions.flat();
    return { data: allData };
  } catch (error) {
    return { error: error.message };
  }
};

// POST method to handle form submission
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { startDate, endDate, account, description, category, minAmount, maxAmount } = body;
    console.log(startDate, endDate, account, description, category, minAmount, maxAmount);

    if (!startDate || !endDate || !account) {
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
    }

    const transactions = await fetchTransactionsFromUPBank(
      startDate,
      endDate,
      account,
      description,
      category,
      minAmount,
      maxAmount
    );

    return NextResponse.json(transactions);
  } catch (error) {
    return NextResponse.json({ error: 'Failed to process request' }, { status: 500 });
  }
}
